export type WorkspaceFeature = {
  title: string;
  description: string;
  status: string;
  available: string[];
  pending: string[];
};

export const accountFeatures: Record<string, WorkspaceFeature> = {
  orders: { title: "我的订单", description: "查看确认、交付和验收中的真实订单。", status: "订单工作台已启用", available: ["订单状态与事件时间线", "取消与验收动作", "桌面和移动布局"], pending: ["支付服务", "真实库存预留", "争议处理"] },
  assets: { title: "我的服务器", description: "查看 SSH 连接命令、租期和续费宽限状态。", status: "SSH 租约工作台已启用", available: ["连接信息", "到期撤权", "2 小时续费宽限期"], pending: ["生产 Agent mTLS 接入", "真实支付 Provider"] },
  wallet: { title: "钱包与流水", description: "查看真实账本余额、冻结额和支付记录。", status: "支付框架已启用，服务商未配置", available: ["双分录账本契约", "支付意图与幂等接口", "真实服务状态渲染"], pending: ["真实支付渠道", "提现与分账渠道", "财务合规确认"] },
  revenue: { title: "收益与返佣", description: "查看已入账收益、结算和返佣记录。", status: "暂无已入账收益", available: ["收益趋势区域", "结算记录", "返佣规则与进度"], pending: ["独立结算 Worker", "双分录账本"] },
  requests: { title: "求购与报价", description: "管理线上求购、线下求购和商家报价。", status: "还没有网站求购", available: ["线上与线下求购分类", "报价比较结构", "状态流转入口"], pending: ["发布表单与审核规则", "通知服务"] },
  referrals: { title: "邀请与记录", description: "查看邀请码、邀请关系和已确认奖励。", status: "暂无网站邀请记录", available: ["邀请链接位置", "规则说明", "邀请记录列表"], pending: ["风控与真实奖励结算"] },
  coupons: { title: "优惠券", description: "管理可用、已使用和已过期优惠券。", status: "暂无网站优惠券", available: ["状态筛选", "适用范围", "到期说明"], pending: ["优惠券发行与核销规则"] },
  "bank-accounts": { title: "银行卡", description: "只展示支付服务商返回的脱敏卡信息。", status: "银行卡服务未配置", available: ["默认卡管理位置", "脱敏展示规则", "解绑确认流程"], pending: ["支付服务商卡 Token", "实名认证审核"] },
  verification: { title: "实名认证", description: "提交个人或企业主体信息，由平台管理员人工核验。", status: "人工 KYC 审核已启用", available: ["证件字段独立加密", "用户端末四位脱敏", "管理员审核与权限门禁"], pending: ["可选的第三方 Hosted KYC", "证件照片私有对象存储"] },
  addresses: { title: "地址管理", description: "维护设备交付和线下采购地址。", status: "地址数据库已启用", available: ["新增、编辑、删除和默认地址", "所有权与版本冲突保护"], pending: ["地址标准化服务"] },
  notifications: { title: "通知中心", description: "查看订单、设备、审核与系统通知。", status: "站内通知已启用", available: ["未读状态、业务跳转和批量已读", "团队与争议通知"], pending: ["邮件与短信发送渠道"] },
  disputes: { title: "订单争议", description: "待验收订单可直接在订单详情中提交交付问题。", status: "争议入口已合并到订单页", available: ["后端校验订单所有权和可争议状态", "展示处理期限和争议原因"], pending: ["独立争议工单列表"] },
  teams: { title: "团队管理", description: "创建团队、邀请成员并分配角色。", status: "团队数据库已启用", available: ["团队成员与邀请", "站内通知联动"], pending: ["细粒度资源授权"] },
  "api-keys": { title: "API Key", description: "管理自动化程序使用的最小权限凭据。", status: "密钥生命周期已启用", available: ["一次性明文", "哈希存储和吊销"], pending: ["API Key 请求认证中间件"] },
  settings: { title: "账户与设置", description: "管理资料、安全、语言、主题和登录设备。", status: "账户安全台已启用", available: ["设备会话管理", "密码修改", "安全 Cookie 会话"], pending: ["邮箱验证", "手机号绑定"] },
};

export const supplierFeatures: Record<string, WorkspaceFeature> = {
  resources: { title: "设备与算力资源", description: "管理设备、库存、价格和上架状态。", status: "尚未通过商家审核", available: ["资源表格", "库存与状态字段", "移动端操作卡片"], pending: ["商家审核", "设备来源审核", "真实库存事务"] },
  orders: { title: "订单与交付", description: "确认接单并更新非敏感交付进度。", status: "订单工作台已启用", available: ["确认与取消", "开始交付与标记已交付", "订单事件时间线"], pending: ["加密凭据存储", "订单争议与超时规则"] },
  revenue: { title: "商家收益与提现", description: "查看 T+1 结算、佣金、冻结余额并提交人工银行转账申请。", status: "人工提现审核已启用", available: ["5% 佣金与 T+1 结算", "争议冻结与双分录余额", "管理员审核及打款登记"], pending: ["银行代付 API", "自动对账"] },
  analytics: { title: "经营统计", description: "查看资源利用率、订单和营收趋势。", status: "暂无可统计的真实数据", available: ["利用率、订单、营收指标结构"], pending: ["独立统计任务"] },
  rebates: { title: "商家返佣", description: "查看阶梯、进度和已结算记录。", status: "暂无已结算返佣", available: ["返佣阶梯", "进度说明", "结算记录"], pending: ["已确认的返佣规则", "结算 Worker"] },
  settings: { title: "商家设置", description: "管理店铺资料、联系人和安全设置。", status: "申请通过后开放", available: ["店铺资料", "联系人", "安全说明"], pending: ["商家审核"] },
};
