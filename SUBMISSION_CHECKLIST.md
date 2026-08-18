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
