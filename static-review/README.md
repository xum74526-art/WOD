# 算力星图静态审核页面

> 标注：**静态审核**

本文件夹是从 Web 的 `/info` 页面单独整理出的静态审核包，用于页面内容、布局和交互审核。它不连接业务后端，不读取正式账户，也不会发送表单或资源数据。

## 使用方式

- 入口文件：`index.html`
- 页面资源：`styles.css`、`showcase.css`、`app.js` 和 `assets/kai-logo.svg`
- 所有资源均使用相对路径，可将整个文件夹单独部署到任意静态托管目录。
- 页面内的需求记录只保存在当前浏览器的 `localStorage`。
- 对外请求已由内容安全策略禁止，页面不依赖 Web API 或后端服务。
- 独立发布项目为 Vercel `static-review`，只部署本文件夹。

本地预览示例：

```powershell
python -m http.server 9200 --directory static-review
```

然后访问 `http://127.0.0.1:9200/`。

## 审核说明

- 审核类型：静态页面审核
- 页面名称：算力星图
- 正式地址：`https://wod.kai.com/info`
- 独立审核地址：`https://static-review.vercel.app`
- 联系电话：`+86 4001082026`
- 网站备案信息：`沪ICP备2026046279号-1`（不以网站 ICP 备案号替代 APP 备案号）。
- 整理日期：2026-09-17
