# 投稿清单

**状态**: 待研究完成后填写 | **项目**: ar-politeia

---

## 投稿包

- 目录: `research/paper/`
- 常见产物: `main.tex` / `prl.tex` / `nature.tex`、`claims.json`、图表与投稿包

## 投稿前人类检查

- [ ] 1. 阅读 cover letter，确认叙述合适
- [ ] 2. 浏览编译后的 PDF，确认无格式异常
- [ ] 3. 确认 authorship
- [ ] 4. 决定主 arXiv / 期刊分类
- [ ] 5. 确认 `audit` 已通过，证据链完整

  ```bash
  scripts/verify-evidence.sh   # 退出码 0 才算通过，非 0 就不进入人类决策
  ```

  它做两件事：先从各 job 的运行记录重导 `research/claims.json` 与
  `research/findings.json`，再跑 `audit` 并写出 `research/reproducibility-bundle.json`。
  两者不能拆开：`audit` 审的是一份**导出**的台账，不重导就审是在核验旧台账。

  通过时 bundle 里有两处必须**读**而不是略过的字段：
  - `adjudicated_failures`——非零退出码但已被显式裁定的 job（当前只有
    `V1-NONFLAT-CALIBRATION-C4`，被 V1B→V1F 链取代）。每一条都带着取代它的 job、
    做出裁定的设计和理由。
  - `jobs_without_manifest`——录了结果但没有 manifest、因而退出码检查看不到的 job
    （当前 6 个，全部早于 manifest 约定）。它们**被报告但不会让 audit 失败**：
    现在补 manifest 等于编造它们的退出码。

## 投稿步骤

```bash
# 1. 生成图表并编译 PDF
cd research/paper
make           # 或 make arxiv / make prl.pdf / make nature.pdf

# 2. 上传到目标期刊或 arXiv
#    以该目录下声明的主 tex 与 figures 为准
```

## 注意

本清单在单研究方案布局下使用。旧的多方向 / synthesis 路径已弃用。
