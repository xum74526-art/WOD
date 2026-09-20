import { pinyin } from 'pinyin-pro'
import type { AppLanguage } from './language.ts'
import { toTraditionalChinese } from './traditional-chinese.ts'

const PERSON_EN: Record<string, string> = {
  '体验用户': 'Demo User',
  'WOD资讯': 'KAI星算 Platform Market',
  'ZTW资讯': 'KAI星算 Platform Market',
  'ZTW資訊': 'KAI星算 Platform Market',
  'KAI星算资讯': 'KAI星算 Platform Market',
  'KAI星算資訊': 'KAI星算 Platform Market',
}

const PLATFORM_NEWS_NAMES = new Set([
  'WOD资讯',
  'ZTW资讯',
  'ZTW資訊',
  'KAI星算资讯',
  'KAI星算資訊',
  'KAI星算平台行情',
  '算力星圖平台行情',
])

const COMMUNITY_EN: Record<string, string> = {
  'H100测评': 'H100 Review',
  '省钱攻略': 'Saving Tips',
  'LLM训练': 'LLM Training',
  'GPU比价': 'GPU Price Comparison',
  '推理优化': 'Inference Optimization',
  '新手提问': 'Beginner Question',
  '收益分享': 'Revenue Sharing',
  '机型对比': 'GPU Comparison',
  '公告': 'Announcement',
  '社区上线了！欢迎大家分享算力使用心得、收益攻略、机型测评。优质内容有奖励！': 'The community is live! Share your compute experience, revenue tips, and GPU reviews. Quality posts can earn rewards.',
  '用A800跑LLM微调，NVLink互联确实快很多。推荐大家用多卡集群模式。': 'I used A800 for LLM fine-tuning. NVLink is noticeably faster. I recommend using a multi-GPU cluster.',
  'RTX 4090现在价格不错，1.98卡时/h，可租81台。建议短线租用做推理，性价比很高。': 'RTX 4090 is well priced right now at 1.98 CH/h, with 81 units available. Short-term rentals are a great value for inference.',
  '刚入了2张H100，跑了3天训练，收益比预期高15%。autodl行情确实稳，分享给大家看看收益曲线。': 'I added two H100 GPUs and ran training for three days. Returns are 15% higher than expected. The autodl market has been stable, so I am sharing the revenue curve.',
  '感谢分享，我也在用这款，确实稳定。': 'Thanks for sharing. I use this model too, and it is very stable.',
  '楼主说得很中肯，收益确实看机型。': 'Good point. Returns really do depend on the GPU model.',
  '同感！我也跑了几天，效果不错。': 'Agreed! I have run it for a few days and the results are good.',
  '请问多久回本？我也想入一张试试。': 'How long does it take to break even? I would like to try one too.',
  'autodl的机器整体质量还是靠谱的。': 'The overall quality of autodl machines is reliable.',
  '收益比预期高这么多？我考虑一下。': 'Are the returns really that much higher than expected? I will consider it.',
  '我也想试试这个型号，预算够的话入一个。': 'I would like to try this model too if my budget allows.',
  '建议楼主多跑几天再评价，数据更准。': 'Run it for a few more days before reviewing it so the data is more accurate.',
  '这个收益算高的了，一般人可能达不到。': 'That is a high return and may not be typical.',
  '稳定性怎么样？有没有经常断线？': 'How stable is it? Does it disconnect often?',
  '同价位感觉这个性价比最高了。': 'This looks like the best value in its price range.',
  '感谢楼主分享实测数据，很有参考价值。': 'Thanks for sharing measured data. It is very useful.',
  '我也在犹豫，看了你的帖子决定入一张。': 'I was undecided, but your post convinced me to get one.',
  '跑训练的话显存够用吗？': 'Is the VRAM sufficient for training?',
  '分区不同价格差异大吗？': 'Do prices vary much by region?',
  '实用！已收藏，回头试试这个技巧。': 'Useful! Saved. I will try this tip later.',
  '太感谢了，正好需要这个省钱攻略。': 'Thank you. This is exactly the saving tip I needed.',
  '这个技巧不错，学到了！': 'Great tip. I learned something new!',
  'mark一下，下次买算力参考。': 'Saved for my next compute purchase.',
  '楼主很专业，谢谢分享省钱方法。': 'Very professional. Thanks for sharing this saving method.',
  '确实，选对区域和机型能省不少。': 'Choosing the right region and model can save a lot.',
  '这个比价信息太有用了，感谢！': 'This price comparison is very useful. Thanks!',
  '请问还有其他省钱技巧吗？': 'Do you have any other saving tips?',
  '已转发给朋友，大家一起省钱。': 'Shared with friends so we can all save.',
  '这个攻略太及时了，正好要下单。': 'Perfect timing. I was just about to place an order.',
  '原来可以这么操作，学到了。': 'I did not know this was possible. Good to know.',
  '建议楼主多分享一些这类攻略。': 'Please share more tips like this.',
  '实操性强，点赞！': 'Very practical. Liked!',
  '这个方法适用于所有机型吗？': 'Does this method work for every GPU model?',
  '太实用了，马上去试试。': 'Very useful. I will try it now.',
  '同问，也想知道这个机型够不够用。': 'Same question. I would also like to know if this model is enough.',
  '12GB做目标检测应该够，YOLO系列没问题。': '12 GB should be enough for object detection, including YOLO models.',
  '建议上大显存的，小显存容易OOM。': 'Choose more VRAM. Smaller cards can easily run out of memory.',
  '看你的batch size，太小容易爆显存。': 'It depends on your batch size. Adjust it to avoid running out of VRAM.',
  '推理没问题，训练可能要减小batch。': 'Inference is fine. You may need a smaller batch for training.',
  '我之前跑过，8GB就够用了。': 'I have run it before, and 8 GB was enough.',
  '要看模型大小，大模型必须大显存。': 'It depends on model size. Large models require more VRAM.',
  '推荐用RTX 4090，性价比高。': 'I recommend RTX 4090 for its strong value.',
  '同价位A100更稳，NVLink互联快。': 'At the same price, A100 is more stable and NVLink is fast.',
  '谢谢各位解答，我去试试。': 'Thanks for the answers. I will give it a try.',
  '建议先用小模型测试一下。': 'Test with a smaller model first.',
  '显存不够可以试试梯度累积。': 'Try gradient accumulation if VRAM is limited.',
  '32GB应该够大部分场景了。': '32 GB should be enough for most workloads.',
  '深度学习训练至少16GB起。': 'Use at least 16 GB for deep learning training.',
  '关注，等楼主后续更新。': 'Following for future updates.',
  '同样预算我选显存大的，灵活性高。': 'With the same budget, I would choose more VRAM for flexibility.',
  '看具体用途，推理选便宜的，训练选大的。': 'It depends on the workload: cheaper for inference, larger for training.',
  '性价比确实重要，但稳定性也要考虑。': 'Value matters, but stability should also be considered.',
  '感谢比价，正好在纠结选哪个。': 'Thanks for the comparison. I was deciding between these options.',
  '我感觉还是选大厂的更靠谱。': 'I think a major vendor is the safer choice.',
  '这个对比很直观，点赞！': 'This comparison is very clear. Liked!',
  '同样预算选显存大的没错。': 'More VRAM is the right choice at the same budget.',
  '价格差异这么大吗？学到了。': 'I did not realize the price difference was this large.',
  '区域不同价格差异确实大。': 'Prices really do vary a lot by region.',
  '选机器还是要看实际需求。': 'Choose a machine based on the actual workload.',
  '楼主比价信息很及时，感谢。': 'This price comparison is timely. Thanks.',
  '我倾向选便宜的，够用就行。': 'I prefer the cheaper option as long as it is sufficient.',
  '看用途吧，不能光看价格。': 'Consider the workload, not just the price.',
  '这个对比对我很有帮助，谢谢。': 'This comparison helped me a lot. Thanks.',
  '关注后续对比，期待更多。': 'Following for more comparisons.',
  '感谢分享！': 'Thanks for sharing!',
  '说得好，赞同。': 'Well said. I agree.',
  '学到了，谢谢。': 'I learned something. Thanks.',
  '支持楼主！': 'Great post!',
  '关注一下，期待更多分享。': 'Following. Looking forward to more posts.',
  '很有参考价值。': 'Very useful information.',
  '楼主专业！': 'Very professional!',
  '这个信息很有用。': 'This information is very useful.',
  '同感同感。': 'Agreed.',
  '已收藏，感谢！': 'Saved. Thanks!',
  '说得在理。': 'That makes sense.',
  '支持社区，一起交流。': 'Supporting the community. Let us keep sharing.',
  '欢迎更多算力相关讨论。': 'More compute discussions are welcome.',
  '点赞支持！': 'Liked!',
  '期待楼主后续更新。': 'Looking forward to future updates.',
  '测试评论！': 'Test comment!',
}

const TERM_EN: Record<string, string> = {
  'LLM微调': 'LLM fine-tuning',
  'Stable Diffusion': 'Stable Diffusion',
  '图像分类': 'image classification',
  '目标检测': 'object detection',
  '语音识别': 'speech recognition',
  '3D渲染': '3D rendering',
  '科学计算': 'scientific computing',
  '深度学习训练': 'deep learning training',
  'AI推理': 'AI inference',
  '很快': 'very fast',
  '稳定': 'stable',
  '中规中矩': 'average',
  '出乎意料地快': 'surprisingly fast',
  '划算': 'excellent',
  '偏贵但值得': 'expensive but worthwhile',
  '性价比高': 'high',
  '一般般': 'average',
  '强烈': 'strongly recommended for',
  '谨慎': 'recommended with caution for',
  '有预算就上': 'recommended if the budget allows for',
  '新手': 'beginner',
  '够用': 'is sufficient',
  '绰绰有余': 'has plenty of headroom',
  '绰绰有ERS': 'has plenty of headroom',
  '有点紧': 'is a little tight',
  '很充裕': 'is more than enough',
  '高15%': '15% higher',
  '差不多': 'about the same',
  '低一点': 'slightly lower',
  '华北': 'North China',
  '华东': 'East China',
  '华中': 'Central China',
  '华南': 'South China',
  '东北': 'Northeast China',
  '西北': 'Northwest China',
  '西南': 'Southwest China',
  '中国大陆': 'Mainland China',
  '亚太': 'Asia Pacific',
  '北美': 'North America',
  '欧洲': 'Europe',
  '中东': 'Middle East',
  '南美': 'South America',
  '非洲': 'Africa',
  '海外': 'Overseas',
  '全球/未披露': 'Global / Undisclosed',
  '全球／未披露': 'Global / Undisclosed',
  '全球 / 未披露': 'Global / Undisclosed',
  '未披露': 'Undisclosed',
}

function term(value: string): string {
  return TERM_EN[value] ?? value
}

function productName(value: string): string {
  return value.replace(/机$/, '')
}

function translateGeneratedPost(source: string): string | null {
  let match = source.match(/^用(.+)跑了一周(.+)，整体体验：速度(.+)，(.+)显存(.+)，价格([\d.]+)卡时(?:卡时)?\/h算(.+)。推荐(.+)使用。$/)
  if (match) return `I used ${productName(match[1])} for ${term(match[2])} for one week. Speed was ${term(match[3])}, ${match[4]} VRAM ${term(match[5])}, and ${match[6]} CH/h offers ${term(match[7])} value. ${term(match[8])} use.`

  match = source.match(/^(.+)到手3天，跑了(.+)训练，显存(.+)，CUDA (.+)。(.+)，性价比(.+)。$/)
  if (match) return `After three days with ${productName(match[1])}, I ran ${term(match[2])} training with ${match[3]} VRAM and CUDA ${match[4]}. ${term(match[5])}, with ${term(match[6])} value.`

  match = source.match(/^刚试了(.+)在(.+)的机器，([\d.]+)卡时(?:卡时)?\/h，(.+)显存。跑(.+)效率比预期(.+)，给个([\d.]+)分。$/)
  if (match) return `I just tested ${productName(match[1])} in ${term(match[2])} at ${match[3]} CH/h with ${match[4]} VRAM. ${term(match[5])} performance was ${term(match[6])} than expected. Rating: ${match[7]}/10.`

  match = source.match(/^(.+)使用小技巧：(.+)显存跑(.+)时，batch size建议设([\d.]+)，能跑满利用率。([\d.]+)卡时(?:卡时)?\/h的机器别浪费。$/)
  if (match) return `${productName(match[1])} tip: with ${match[2]} VRAM for ${term(match[3])}, set the batch size to ${match[4]} for full utilization. Make the most of a machine priced at ${match[5]} CH/h.`

  match = source.match(/^省钱攻略：(.+)在(.+)的机器最便宜，([\d.]+)卡时(?:卡时)?\/h，比同型号其他地区便宜不少。$/)
  if (match) return `Saving tip: ${productName(match[1])} is cheapest in ${term(match[2])} at ${match[3]} CH/h, well below other regions for the same model.`

  match = source.match(/^刚发现(.+)可租([\d.]+)台，([\d.]+)卡时(?:卡时)?\/h，做(.+)推理完全够用，不用上更贵的卡。$/)
  if (match) return `I found ${productName(match[1])} with ${match[2]} units available at ${match[3]} CH/h. It is sufficient for ${term(match[4])} inference, so a more expensive GPU is unnecessary.`

  match = source.match(/^请教各位，(.+)（(.+)显存）跑(.+)，需要装什么环境？CUDA (.+)够用吗？$/)
  if (match) return `What environment should I install to run ${term(match[3])} on ${productName(match[1])} with ${match[2]} VRAM? Is CUDA ${match[4]} sufficient?`

  match = source.match(/^(.+) ([\d.]+)卡时(?:卡时)?\/h vs 同型号其他平台，这个价格合理吗？有没有更便宜的渠道？$/)
  if (match) return `${productName(match[1])} costs ${match[2]} CH/h. Is that reasonable compared with other platforms, or is there a cheaper option?`

  match = source.match(/^打算用(.+)做(.+)，(.+)显存够吗？求大佬指点。$/)
  if (match) return `I plan to use ${productName(match[1])} for ${term(match[2])}. Is ${match[3]} VRAM enough? Advice is welcome.`

  match = source.match(/^(.+) vs (.+)：都是做(.+)，(.+) vs (.+)显存，价格([\d.]+)(?:卡时)? vs ([\d.]+)卡时(?:卡时)?\/h。大家选哪个？$/)
  if (match) return `${productName(match[1])} vs ${productName(match[2])} for ${term(match[3])}: ${match[4]} vs ${match[5]} VRAM, priced at ${match[6]} vs ${match[7]} CH/h. Which would you choose?`

  match = source.match(/^算力比价：(.+) ([\d.]+)卡时(?:卡时)?\/h，([\d.]+)台可租。同样预算你们选这张卡还是别的？$/)
  if (match) return `Compute price comparison: ${productName(match[1])} at ${match[2]} CH/h, with ${match[3]} units available. Would you choose this GPU on the same budget?`

  return null
}

export function localizePersonName(value: string, lang: AppLanguage): string {
  if (!value) return value
  if (PLATFORM_NEWS_NAMES.has(value)) {
    return lang === 'en' ? 'KAI星算 Platform Market' : lang === 'zh-Hant' ? '算力星圖平台行情' : 'KAI星算平台行情'
  }
  if (lang === 'zh-Hans') return value
  if (lang === 'zh-Hant') return value === '体验用户' ? toTraditionalChinese(value) : value
  if (PERSON_EN[value]) return PERSON_EN[value]
  if (!/^[\u3400-\u9fff·]{2,12}$/.test(value)) return value

  const words = pinyin(value, { toneType: 'none', type: 'array' }).filter(Boolean)
  if (!words.length) return value
  const surname = words[0].charAt(0).toUpperCase() + words[0].slice(1)
  const given = words.slice(1).join('')
  return given ? `${surname} ${given.charAt(0).toUpperCase()}${given.slice(1)}` : surname
}

/**
 * Localize a stored nickname for display without changing the account value.
 * Once the user edits the field, their input is shown verbatim.
 */
export function profileUsernameDisplayValue(
  originalUsername: string,
  editedUsername: string,
  usernameEdited: boolean,
  lang: AppLanguage,
): string {
  return usernameEdited
    ? editedUsername
    : localizePersonName(originalUsername, lang)
}

/** Preserve the stored nickname when a localized display value was not edited. */
export function profileUsernameSubmissionValue(
  originalUsername: string,
  editedUsername: string,
  usernameEdited: boolean,
): string {
  return usernameEdited ? editedUsername : originalUsername
}

export function localizeCommunityText(value: string, lang: AppLanguage): string {
  if (!value || lang === 'zh-Hans') return value
  if (lang === 'zh-Hant') return toTraditionalChinese(value)
  return COMMUNITY_EN[value] ?? translateGeneratedPost(value) ?? value
}

/** Rename only historical first-party news copy; never rewrite user-authored content. */
export function localizeInternalBrandText(value: string, sourceKey?: string | null): string {
  if (!value || sourceKey !== 'wod-market') return value
  return value.replace(/(?:WOD|ZTW)(?![A-Z0-9_-])/g, 'KAI星算')
}

export function localizeProductName(value: string | null | undefined, lang: AppLanguage): string {
  const source = value || ''
  if (lang === 'en') return productName(source)
  return lang === 'zh-Hant' ? toTraditionalChinese(source) : source
}
