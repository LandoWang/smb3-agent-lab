# SMB3 Agent Lab

用《超级马里奥兄弟 3》研究规划、低延迟控制与可审计的智能体实验。

这是研究预览版，不是全游戏通关器，也不是强化学习 SOTA 声明。

## 已有内容

- 记录 Astra + OpenRouter Jev、本地 DiffusionGemma、CLM 的不同实验；明确区分模型身份与执行来源。
- 发布第三方 MarioDQN 权重的四次单局复现结果、按键日志和录像。
- 提供可移植的 CPU DQN 执行器，以及不依赖 ROM 的日志校验工具。
- 新增 [通用 Session Adapter](adapter/README.md)：帧推进、分层计划、动作选择、三条时序、回放、打包和离线测试；包含 Codex、OpenRouter Jev 与本地 DiffusionGemma 的客户端。
- 总结内存字段、跳跃物理、顶砖角修正与地图加载的验证边界。

## 真实结果

同一份第三方 DQN 权重、seed=1，不训练、不自动重试：

| 关卡 | 游戏内时间 | 最远前进 | 结果 |
|---|---:|---:|---|
| W1-1 | 19.12 秒 | 2658 像素 | 已通过；另用 300 帧无按键观察确认 COURSE CLEAR |
| W1-3 | 11.13 秒 | 491 像素 | 台阶处停滞，没死 |
| W1 堡垒 | 5.05 秒 | 170 像素 | 石阶处停滞，没死 |
| W1 飞船 | 15.67 秒 | 548 像素 | 受伤变小，炮管处停滞，没死 |

后三次由原作者的“181 帧未刷新最远 X”规则停止，不代表永远无法通过。各关初始服装不同，不是严格控制变量的泛化基准。

录像：[W1-1](assets/w1-1-with-clear.mp4) · [W1-3](assets/w1-3.mp4) · [堡垒](assets/fortress.mp4) · [飞船](assets/airship.mp4)

## 边界

**DQN 只看四帧灰度图，奖励、停止和审计使用只读内存。** Astra/Jev 系列则直接使用内存辅助观察。两者不能笼统称作同一种“纯视觉玩法”。

Jev 接管 DQN、目标条件 DQN 尚未实现。分层 Session Adapter 的核心与远程客户端已公开；游戏内存 harness、模拟器和模型服务仍需单独配置，不是一键通关服务。[两次试跑与掉坑分析](docs/adapter-results.md)明确区分普通内存辅助和移除敌人的作弊消融。

离线试用不需要 ROM、GPU、密钥，也不会调用付费模型：

```sh
cd adapter
python3 -m unittest discover -s tests -v
python3 -m session_adapter demo --output ../output/adapter-demo
```

演示是脚本控制的合成环境，不是马里奥模型实测。私有 Session 包可能含个人信息、内存和存档，不能未经检查公开上传。

不提供 ROM、模型权重、存档、完整地图图像、私有部署、密钥或个人工作目录。第三方 DQN 上游在所核验版本没有明确许可证，因此不重新分发它的源码或权重，只给出处和哈希。

详细说明：[架构与历史](docs/architecture.md) · [结果](docs/results.md) · [复现](docs/reproduce.md) · [内存与物理](docs/memory-and-physics.md)。
