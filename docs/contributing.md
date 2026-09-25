# 参与开发

Python 3.11+，无需安装第三方包：

```bash
python -m unittest discover -s tests -v
python -m manju validate examples/episode.json
python -m manju build examples/episode.json --out output/check-001
```

CI 配置使用 Linux / Windows、Python 3.11 / 3.14。不要以“能导入”代替实际 CLI 与导出检查。

可选在虚拟环境执行 `python -m pip install -e .` 安装 `manju` 命令。构建需要 setuptools；直接运行模块不需要安装或访问包索引。

## 提交约定

1. 每次围绕一个可验收任务，优先使用功能分支和 PR。
2. 修复输入、时间线、输出问题时增加对应回归测试。
3. `planner.py` 保持纯函数；网络、密钥和 SDK 留在未来接入层。
4. 格式变化同时更新示例、字段文档和版本策略。
5. 提交前运行测试及示例，检查 `git diff --check` 和 `git status`。
6. 新依赖说明用途；付费操作应有任务预览、重试和预算边界。

## 问题报告

记录命令、Python/系统版本、期待与实际结果。仅提供可公开的最小剧本，删除凭据和私人资料。问题模板在 `.github/ISSUE_TEMPLATE/`。

## 限制

不判断剧情收益，不自动拆镜，不调用生成/发布 API，不测量音频时长，不保证图片角色一致，不回写 CSV 修改，不恢复生成任务，不提供云备份。按任务清单逐步增加能力，并以真实样片验收。
