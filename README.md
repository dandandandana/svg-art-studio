# SVG 绘画工作室

一个可重复使用的 Codex Skill。用“帮我画图”这样的普通表达开始，把描述、角色卡或参考图转化为精细、可编辑的原生 SVG 插画，并保存真实的制作过程。

## 使用方式

将仓库中 `skills/svg-art-studio/` 的完整目录放入 Codex 的个人 Skills 目录；不要只复制 `SKILL.md`。也可以让 Skill Installer 从本仓库安装 `skills/svg-art-studio`。

明确调用示例：

```text
$svg-art-studio 帮我画一只小狐狸。
```

信息不足时，Skill 会先用通俗问题询问画风、姿势等关键偏好。已经说明的内容不重复问，也可以回答“你来定”。普通绘画参数与实现细节由 agent 处理。

## 绘制与交付

- 实际查看参考，按本次题材研究绘画方法。
- 直接用代码构建原生 SVG，不调用图像生成模型代替绘制。
- 分批绘制、实际渲染并看图修改，保存当时的真实状态。
- 默认交付可编辑 SVG、长边 3000 像素的 PNG，以及 MP4/WebM 制作过程回放；无法导出视频时提供离线 HTML。
- 不预设固定画风、元素数量或视觉重点，不用成稿拆层动画冒充创作过程。

入口说明见 [`SKILL.md`](skills/svg-art-studio/SKILL.md)，记录与导出说明见 [`process-recording.md`](skills/svg-art-studio/references/process-recording.md)。

## 配套工具与检查

`record_process.py` 使用 Python 3 标准库，保存传入的 SVG/PNG 批次快照，并生成可离线播放的 HTML。它不负责绘画、SVG 渲染或视频编码；这些工作由使用 Skill 的 agent 结合可用工具完成。

```text
python skills/svg-art-studio/scripts/record_process.py --help
python -B -m unittest discover -s skills/svg-art-studio/tests -v
```

测试覆盖历史快照保留、重复记录拒绝、损坏检测、成稿一致性和无效输入。简单形状样例已完成浏览器回放检查；完整插画的创作效果尚未实测。
