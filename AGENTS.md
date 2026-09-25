# 项目开发约定

- 面向个人创作者，用户文档和业务错误优先中文。
- 当前仅离线规划和导出，不能把提示词、估时字幕或待生成路径描述成已有素材。
- 修改前阅读 README、docs/architecture.md 及相关格式说明，保留版本语义。
- planner.py 保持纯函数；文件写入在 exporter.py，命令交互在 cli.py。
- 不提交凭据、账号 Cookie、私人剧本、付费素材或生成媒体。
- 默认零运行依赖；新增服务先说明需要、失败处理和成本边界。
- 验证：python -m unittest discover -s tests -v；python -m manju validate examples/episode.json。
- 端到端：python -m manju build examples/episode.json --out output/<新的目录名>；旧目录不能被覆盖。
- 格式及行为变化同时更新示例、文档和有意义的回归测试。
