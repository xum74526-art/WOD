import { request, upload } from './request'

export interface PostItem {
  id: number
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

export function getPosts(tab: string = 'recommend', page: number = 1, keyword: string = '') {
  return request<{ items: PostItem[]; total: number; page: number; page_size: number }>({
    url: '/community/posts', data: { tab, page, keyword },
  })
}

export function getPostDetail(id: number) {
  return request<PostItem>({ url: `/community/posts/${id}` })
}

export interface CommunityMediaUpload {
  url: string
  kind: 'image' | 'video'
  content_type: string
  size: number
  duration?: number | null
  standardized?: boolean
}

export function uploadCommunityMedia(filePath: string, onProgress?: (progress: number) => void) {
  return upload<CommunityMediaUpload>({
    url: '/community/media/upload',
    filePath,
    name: 'media',
    silent: true,
    timeout: 240000,
    onProgress,
  })
}

export function createPost(data: {
  content: string
  images?: string[]
  video?: string
  video_duration?: number
  topic?: string
}) {
  return request<PostItem>({ url: '/community/posts', method: 'POST', data })
}

export function setLike(id: number, liked: boolean) {
  return request<{ liked: boolean; likes: number }>({
    url: `/community/posts/${id}/like`,
    method: 'POST',
    data: { liked },
    retryUncertainOnce: true,
  })
}

export function getComments(id: number) {
  return request<CommentItem[]>({ url: `/community/posts/${id}/comments` })
}

export function createComment(id: number, content: string) {
  return request<CommentItem>({ url: `/community/posts/${id}/comments`, method: 'POST', data: { content } })
}

export function setFollow(uid: number, following: boolean) {
  return request<{ following: boolean }>({
    url: `/community/users/${uid}/follow`,
    method: 'POST',
    data: { following },
    retryUncertainOnce: true,
  })
}
