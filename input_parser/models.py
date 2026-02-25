"""S11 数据模型 — StandardizedInput 及其子结构"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BasicInfo:
    """工程基本信息。

    Attributes:
        project_name: 工程名称（必填）
        project_type: 工程类型（必填），如 "输电线路"、"变电站"
        location: 工程地点
        scale: 工程规模描述
    """

    project_name: str = ""
    project_type: str = ""
    location: str = ""
    scale: str = ""

    def to_dict(self) -> dict[str, str]:
        """转换为字典。"""
        return {
            "project_name": self.project_name,
            "project_type": self.project_type,
            "location": self.location,
            "scale": self.scale,
        }


@dataclass
class TechnicalInfo:
    """技术条件信息。

    Attributes:
        geology: 地质条件
        climate: 气候条件
        special_requirements: 特殊技术要求
    """

    geology: str = ""
    climate: str = ""
    special_requirements: str = ""

    def to_dict(self) -> dict[str, str]:
        """转换为字典。"""
        return {
            "geology": self.geology,
            "climate": self.climate,
            "special_requirements": self.special_requirements,
        }


@dataclass
class ParticipantInfo:
    """参建单位信息。

    Attributes:
        owner: 建设单位
        contractor: 施工单位
        supervisor: 监理单位
        designer: 设计单位
    """

    owner: str = ""
    contractor: str = ""
    supervisor: str = ""
    designer: str = ""

    def to_dict(self) -> dict[str, str]:
        """转换为字典。"""
        return {
            "owner": self.owner,
            "contractor": self.contractor,
            "supervisor": self.supervisor,
            "designer": self.designer,
        }


@dataclass
class ConstraintInfo:
    """约束条件。

    Attributes:
        timeline: 工期要求
        budget: 预算约束
        risks: 已知风险列表
    """

    timeline: str = ""
    budget: str = ""
    risks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "timeline": self.timeline,
            "budget": self.budget,
            "risks": list(self.risks),
        }


@dataclass
class StandardizedInput:
    """标准化输入 — 生成系统统一入口数据结构。

    将 JSON / 自然语言 / PDF 三种输入统一为此结构，
    供下游 GenerationCoordinator 和各章节 Agent 消费。

    Attributes:
        basic: 工程基本信息（project_name 和 project_type 为必填）
        technical: 技术条件信息
        participants: 参建单位信息
        constraints: 约束条件
    """

    basic: BasicInfo = field(default_factory=BasicInfo)
    technical: TechnicalInfo = field(default_factory=TechnicalInfo)
    participants: ParticipantInfo = field(default_factory=ParticipantInfo)
    constraints: ConstraintInfo = field(default_factory=ConstraintInfo)

    def to_dict(self) -> dict[str, Any]:
        """转换为嵌套字典。"""
        return {
            "basic": self.basic.to_dict(),
            "technical": self.technical.to_dict(),
            "participants": self.participants.to_dict(),
            "constraints": self.constraints.to_dict(),
        }

    def validate(self) -> list[str]:
        """校验必填字段，返回错误消息列表。

        Returns:
            错误消息列表，空列表表示校验通过。
        """
        errors: list[str] = []
        if not self.basic.project_name.strip():
            errors.append("basic.project_name 为必填字段")
        if not self.basic.project_type.strip():
            errors.append("basic.project_type 为必填字段")
        return errors
