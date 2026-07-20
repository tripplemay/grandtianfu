# spike L0/L1 A/B 出图汇总

| 场景 | 引导 | 后端 | 出图 | score | 自动验收 | 失败类型 | fail_reasons | tokens | fal像素 | 耗时s | 文件 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| guest2_coarse | L0 | relay | ✅ | 1.0 | ✅ | — | — | 4728 | — | 151.8 | guest2_coarse_L0_relay.png |
| guest2_coarse | L1 | relay | ✅ | 0.85 | ❌ | 结构改动 | 盒区外出现新结构 (新边缘坏块 9/47) | 4784 | — | 178.5 | guest2_coarse_L1_relay.png |
| live_leastbad | L0 | relay | ✅ | 1.0 | ✅ | — | — | 4781 | — | 139.5 | live_leastbad_L0_relay.png |
| live_leastbad | L1 | relay | ✅ | 0.917 | ❌ | 结构改动 | 盒区外出现新结构 (新边缘坏块 5/107) | 4784 | — | 153.8 | live_leastbad_L1_relay.png |

## 预算记账
- 出图 4/4 成功
- relay tokens 合计: 19077
- fal 输出像素合计: 0.00 MP (按 fal 模型单价换算费用)
