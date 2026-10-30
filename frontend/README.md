# 两条软件业务线的 React 应用

公共壳、Login、Family 属账户模块；Dashboard、Analyze、Records、Waveform 属记录模块。双方各自维护对应业务接口，不把全部页面交给一人。

在本目录 npm ci 后 npm run dev。构建 npm run build。API 代理见 vite.config.ts（/api 转发到后端）；当前分析后台执行，页面按 URL 的 task 参数轮询并支持刷新继续查询，历史支持分页、趋势汇总、本人 CSV 导出和删除。API 代理配置见 vite.config.ts；用户会话存 sessionStorage，刷新后可继续会话；服务退出登录后 token 失效。合成波形有明确来源，无模型时显示空分类。

总体分工以[根 README](../README.md)为准。当前详情可展示可选分类器的心率与解释字段；默认无模型时明确显示不可分类说明。展示字段不代表真实模型效果已经验收。
