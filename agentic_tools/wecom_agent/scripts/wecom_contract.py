"""Shared user-facing contract for the LabCanvas WeCom transports."""

from __future__ import annotations


LABAGENT_GUIDE_VERSION = "v1"


def labagent_welcome_message() -> str:
    return (
        "LabAgent 已连接。请直接发送你想完成的任务，例如：\n"
        "- 文献调研、研究方案、开放获取论文与带引用 PDF\n"
        "- Markdown/TeX/PDF、可编辑论文图和科学插图\n"
        "- CAD/PCB、Blender 或实验装置设计\n"
        "- #daily 你的主题（设置每日研究跟踪）\n"
        "结果和文件会回到当前群。视频发布和其他公开发布不在此机器人范围内。"
    )
