# Web 商品图片

`gpu/` 保存与 iOS、Android 相同的 72 张已授权 GPU 图片，`gpu.png` 是项目自有的中性回退图。

`apps/web/lib/product-image.ts` 只接受 API 的 `/static/gpu/<型号>.<扩展名>` 或 Web 的
`/images/gpu/<型号>.<扩展名>` 本地路径，并把它们解析到明确允许的规范文件。外部 URL、路径穿越、
带查询参数的路径或无效值必须按精确 GPU 型号回退；无法识别型号时使用 `gpu.png`。新增或替换图片时，
应先确认使用授权，再同步更新 Web、iOS、Android 的白名单、署名和测试。
