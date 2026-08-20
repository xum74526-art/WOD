import { request } from './request'
import { articlePreview } from '@/utils/article-content'

export interface PostItem {
  id: number | string
  user_id: number
  content: string
  images?: string[] | null
  video?: string | null
  video_duration?: number | null
  topic?: string | null
  content_en?: string | null
  topic_en?: string | null
  origin?: 'user' | 'aggregated' | 'internal' | null
  content_type?: 'text' | 'image' | 'article' | 'video' | null
  source_key?: string | null
  source_name?: string | null
  source_url?: string | null
  source_item_id?: string | null
  source_author?: string | null
  source_published_at?: string | null
  summary?: string | null
  rights_status?: 'pending' | 'allowed' | 'blocked' | null
  video_provider?: string | null
  video_id?: string | null
  video_url?: string | null
  embed_url?: string | null
  thumbnail_url?: string | null
  canonical_url?: string | null
  publish_batch?: string | null
  likes: number
  comments: number
  shares: number
  created_at?: string
  author_name?: string
  author_avatar?: string
  is_liked: boolean
  is_favorited: boolean
  is_following: boolean
  is_own: boolean
}

export interface CommentItem {
  id: number
  post_id: number
  user_id: number
  content: string
  created_at?: string
  author_name?: string
}

interface CanonicalArticle {
  id: number
  title: string
  summary?: string | null
  content?: string | null
  content_format?: 'html' | 'text' | null
  content_type: 'article'
  image_url?: string | null
  original_url?: string | null
  published_at?: string | null
  view_count?: number
  source?: { name?: string; site_url?: string }
  is_favorited?: boolean
}

interface CanonicalVideo {
  id: string
  title: string
  summary: string
  category: string
  platform: string
  published_at?: string | null
  duration?: string | null
  thumbnail_url?: string | null
  embed_url?: string | null
  original_url?: string | null
  content_type: 'video'
  is_favorited?: boolean
}

interface CanonicalComment {
  id: number
  content: string
  created_at?: string
  is_own?: boolean
  author?: { display_name?: string }
}

function articleToPost(article: CanonicalArticle, preview = false): PostItem {
  return {
    id: article.id,
    user_id: 0,
    content: preview
      ? articlePreview(article.summary, article.content, article.title)
      : article.content || article.summary || article.title,
    images: article.image_url ? [article.image_url] : [],
    topic: article.title,
    origin: 'aggregated',
    content_type: article.content_type || 'article',
    source_name: article.source?.name || null,
    source_url: article.original_url || article.source?.site_url || null,
    summary: articlePreview(article.summary, article.content, article.title) || null,
    rights_status: 'allowed',
    likes: 0,
    comments: 0,
    shares: 0,
    created_at: article.published_at || undefined,
    author_name: article.source?.name || 'KAI',
    is_liked: false,
    is_favorited: Boolean(article.is_favorited),
    is_following: false,
    is_own: false,
  }
}

function videoToPost(video: CanonicalVideo): PostItem {
  return {
    id: video.id,
    user_id: 0,
    content: articlePreview(video.summary, null, video.title),
    images: [],
    topic: video.title,
    origin: 'internal',
    content_type: 'video',
    source_name: video.platform,
    source_url: video.original_url || null,
    summary: articlePreview(video.summary, null, video.title),
    video_provider: video.embed_url?.includes('youtube') ? 'youtube' : null,
    video_id: video.id,
    video_url: video.original_url || null,
    embed_url: video.embed_url || null,
    thumbnail_url: video.thumbnail_url || null,
    likes: 0,
    comments: 0,
    shares: 0,
    created_at: video.published_at || undefined,
    author_name: video.platform || 'KAI',
    is_liked: false,
    is_favorited: Boolean(video.is_favorited),
    is_following: false,
    is_own: false,
  }
}

function canonicalComment(row: CanonicalComment, postId: number): CommentItem {
  return {
    id: row.id,
    post_id: postId,
    user_id: 0,
    content: row.content,
    created_at: row.created_at,
    author_name: row.author?.display_name || '',
  }
}

export type CommunityFeed = 'recommend' | 'follow' | 'latest' | 'video'

export async function getPosts(feed: CommunityFeed = 'recommend', page: number = 1, keyword: string = '') {
  const normalizedKeyword = keyword.trim().toLowerCase()
  let rows: Array<CanonicalArticle | CanonicalVideo>
  if (feed === 'recommend') {
    rows = await request<Array<CanonicalArticle | CanonicalVideo>>({ url: '/feed/recommended' })
  } else if (feed === 'follow') {
    rows = await request<Array<CanonicalArticle | CanonicalVideo>>({ url: '/favorites' })
  } else {
    rows = await request<Array<CanonicalArticle | CanonicalVideo>>({
      url: '/feed/latest',
      data: feed === 'video' ? { content_type: 'video' } : undefined,
    })
  }
  const matched = rows.filter((item) => {
    if (!normalizedKeyword) return true
    const source = item.content_type === 'video' ? item.platform : item.source?.name || ''
    return `${item.title} ${item.summary || ''} ${source}`.toLowerCase().includes(normalizedKeyword)
  })
  const items = matched.map(item => item.content_type === 'video' ? videoToPost(item) : articleToPost(item, true))
  return {
    items,
    total: items.length,
    page: 1,
    page_size: items.length,
  }
}

export function getPostDetail(id: number) {
  return request<CanonicalArticle>({ url: `/public/news/${id}` }).then(articleToPost)
}

export function getVideoDetail(id: string) {
  return request<CanonicalVideo>({ url: `/public/videos/${encodeURIComponent(id)}` }).then(videoToPost)
}

export function setContentFavorite(contentType: 'article' | 'video', id: string | number, favorited: boolean) {
  if (favorited) {
    return request<{ content_type: string; content_id: string; is_favorited: boolean }>({
      url: `/favorites/${contentType}/${encodeURIComponent(String(id))}`,
      method: 'POST',
    })
  }
  return request<{ content_type: string; content_id: string; is_favorited: boolean }>({
    url: `/favorites/${contentType}/${encodeURIComponent(String(id))}`,
    method: 'DELETE',
  })
}

export interface CommunityMediaUpload {
  url: string
  kind: 'image' | 'video'
  content_type: string
  size: number
}

export function uploadCommunityMedia(filePath: string) {
  return Promise.reject(new Error('统一资讯社区暂不支持用户媒体上传')) as Promise<CommunityMediaUpload>
}

export function createPost(data: {
  content: string
  images?: string[]
  video?: string
  video_duration?: number
  topic?: string
}) {
  return Promise.reject(new Error('统一资讯社区暂不支持用户发帖')) as Promise<PostItem>
}

export function toggleLike(id: number) {
  return Promise.resolve({ liked: false, likes: 0 })
}

export function getComments(id: number) {
  return request<CanonicalComment[]>({ url: `/public/news/${id}/comments` })
    .then(rows => rows.map(row => canonicalComment(row, id)))
}

export function createComment(id: number, content: string) {
  return request<CanonicalComment>({ url: `/news/${id}/comments`, method: 'POST', data: { content } })
    .then(row => canonicalComment(row, id))
}

export function toggleFollow(uid: number) {
  return Promise.resolve({ following: false })
}
