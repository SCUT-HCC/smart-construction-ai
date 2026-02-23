#!/usr/bin/env python3
"""
施工方案章节结构分析脚本
分析16份施工方案文档的章节结构，提取章节频率、命名变体、典型顺序等信息
"""

import re
from collections import defaultdict, Counter
from pathlib import Path
from typing import Dict, List, Tuple
import json

def extract_chapters_from_file(file_path: Path) -> List[Tuple[int, str, str]]:
    """
    从文件中提取章节标题
    返回: [(level, title, normalized_title), ...]
    level: 1=一级标题, 2=二级标题, 3=三级标题
    """
    chapters = []

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 匹配markdown标题
        for line in content.split('\n'):
            # 匹配 # 标题
            match = re.match(r'^(#{1,3})\s+(.+)$', line.strip())
            if match:
                level = len(match.group(1))
                title = match.group(2).strip()

                # 跳过一些非章节标题
                if any(skip in title.lower() for skip in ['目录', '表', '图', '附件', 'gis', '500kv', '电白', '广东电网', '中国南方电网']):
                    continue

                # 标准化标题：去除序号
                normalized = re.sub(r'^[一二三四五六七八九十\d]+[、\.\s]', '', title)
                normalized = re.sub(r'^\d+(\.\d+)*\s*', '', normalized)
                normalized = normalized.strip()

                if normalized:
                    chapters.append((level, title, normalized))
    except Exception as e:
        print(f"读取文件 {file_path} 失败: {e}")

    return chapters


def normalize_chapter_name(name: str) -> str:
    """标准化章节名称，用于识别同义章节"""
    # 去除常见后缀
    name = re.sub(r'(措施|要求|管理|内容|说明|方案|计划)$', '', name)
    # 去除括号内容
    name = re.sub(r'[（(].*?[）)]', '', name)
    name = name.strip()
    return name


def analyze_chapters(output_dir: Path) -> Dict:
    """分析所有文档的章节结构"""

    all_chapters = defaultdict(list)  # {doc_id: [(level, title, normalized_title), ...]}
    level1_counter = Counter()  # 一级章节频率统计
    level2_by_level1 = defaultdict(Counter)  # 每个一级章节下的二级章节
    chapter_variants = defaultdict(set)  # 章节命名变体

    # 读取16份文档
    for i in range(1, 17):
        final_md = output_dir / str(i) / 'final.md'
        if final_md.exists():
            chapters = extract_chapters_from_file(final_md)
            all_chapters[i] = chapters

            # 统计一级章节
            current_level1 = None
            for level, title, normalized in chapters:
                if level == 1:
                    # 统计一级章节
                    std_name = normalize_chapter_name(normalized)
                    level1_counter[std_name] += 1
                    chapter_variants[std_name].add(normalized)
                    current_level1 = std_name
                elif level == 2 and current_level1:
                    # 统计二级章节
                    std_name = normalize_chapter_name(normalized)
                    level2_by_level1[current_level1][std_name] += 1
        else:
            print(f"文档 {i} 不存在")

    return {
        'all_chapters': dict(all_chapters),
        'level1_counter': level1_counter,
        'level2_by_level1': dict(level2_by_level1),
        'chapter_variants': {k: list(v) for k, v in chapter_variants.items()}
    }


def generate_report(analysis: Dict, output_file: Path):
    """生成分析报告"""

    report = []
    report.append("# 施工方案章节结构分析报告\n")
    report.append("## 一、章节出现频率统计\n")
    report.append("### 1.1 一级章节频率表\n")
    report.append("| 章节名称（标准化） | 出现次数 | 覆盖率 | 命名变体 |")
    report.append("|---|---|---|---|")

    level1_counter = analysis['level1_counter']
    chapter_variants = analysis['chapter_variants']

    # 按频率降序排列
    for chapter, count in level1_counter.most_common():
        coverage = f"{count}/16 ({count/16*100:.1f}%)"
        variants = '、'.join(chapter_variants[chapter])
        report.append(f"| {chapter} | {count} | {coverage} | {variants} |")

    report.append("\n### 1.2 核心章节识别\n")
    report.append("**必备章节（出现≥12次，覆盖率≥75%）**:\n")
    mandatory = [ch for ch, cnt in level1_counter.items() if cnt >= 12]
    for ch in mandatory:
        count = level1_counter[ch]
        report.append(f"- {ch} ({count}/16, {count/16*100:.1f}%)")

    report.append("\n**常见章节（出现6-11次，覆盖率37.5%-68.75%）**:\n")
    common = [ch for ch, cnt in level1_counter.items() if 6 <= cnt < 12]
    for ch in common:
        count = level1_counter[ch]
        report.append(f"- {ch} ({count}/16, {count/16*100:.1f}%)")

    report.append("\n**可选章节（出现<6次，覆盖率<37.5%）**:\n")
    optional = [ch for ch, cnt in level1_counter.items() if cnt < 6]
    for ch in optional:
        count = level1_counter[ch]
        report.append(f"- {ch} ({count}/16, {count/16*100:.1f}%)")

    report.append("\n## 二、典型章节顺序分析\n")
    report.append("基于16份文档，提取最常见的章节顺序模式：\n\n")

    # 分析章节顺序
    all_sequences = []
    for doc_id, chapters in analysis['all_chapters'].items():
        sequence = [normalize_chapter_name(norm) for lvl, _, norm in chapters if lvl == 1]
        all_sequences.append(sequence)

    # 统计最常见的前5个章节顺序
    report.append("### 2.1 文档开头常见章节顺序\n")
    first_chapters = Counter()
    for seq in all_sequences:
        if len(seq) >= 1:
            first_chapters[seq[0]] += 1

    report.append("**第一章节**:\n")
    for ch, cnt in first_chapters.most_common(5):
        report.append(f"- {ch} ({cnt}次)")

    second_chapters = Counter()
    for seq in all_sequences:
        if len(seq) >= 2:
            second_chapters[seq[1]] += 1

    report.append("\n**第二章节**:\n")
    for ch, cnt in second_chapters.most_common(5):
        report.append(f"- {ch} ({cnt}次)")

    third_chapters = Counter()
    for seq in all_sequences:
        if len(seq) >= 3:
            third_chapters[seq[2]] += 1

    report.append("\n**第三章节**:\n")
    for ch, cnt in third_chapters.most_common(5):
        report.append(f"- {ch} ({cnt}次)")

    report.append("\n## 三、子章节结构分析\n")
    level2_by_level1 = analysis['level2_by_level1']

    # 选取频率最高的5个一级章节分析其子章节
    top5_level1 = [ch for ch, _ in level1_counter.most_common(10)]

    for level1_ch in top5_level1:
        if level1_ch in level2_by_level1:
            report.append(f"\n### 3.{top5_level1.index(level1_ch)+1} {level1_ch}\n")
            report.append("| 二级章节 | 出现次数 |")
            report.append("|---|---|")

            level2_counter = level2_by_level1[level1_ch]
            for level2_ch, cnt in level2_counter.most_common(10):
                report.append(f"| {level2_ch} | {cnt} |")

    report.append("\n## 四、命名变体识别\n")
    report.append("识别出的主要章节命名变体：\n\n")

    # 只显示有多个变体的章节
    for std_name, variants in sorted(chapter_variants.items(), key=lambda x: len(x[1]), reverse=True):
        if len(variants) > 1:
            report.append(f"**{std_name}**:\n")
            for var in sorted(variants):
                report.append(f"- {var}")
            report.append("")

    report.append("\n## 五、与标准7章节模板对比\n")
    report.append("根据 `templates/standard_50502.md` 的7章节标准：\n\n")
    report.append("1. 编制依据\n")
    report.append("2. 工程概况\n")
    report.append("3. 施工安排\n")
    report.append("4. 施工准备\n")
    report.append("5. 施工方法及工艺要求\n")
    report.append("6. 施工保证措施\n")
    report.append("7. 应急预案\n\n")

    report.append("### 5.1 实际文档与标准模板的对比\n\n")

    standard_7 = {
        '编制依据': '编制依据',
        '工程概况': '工程概况',
        '施工安排': '施工安排',
        '施工准备': '施工准备',
        '施工方法': '施工方法及工艺要求',
        '施工保证措施': '施工保证措施',
        '应急预案': '应急预案'
    }

    report.append("| 标准章节 | 实际文档中的对应章节 | 出现频率 | 状态 |")
    report.append("|---|---|---|---|")

    for std_key, std_name in standard_7.items():
        # 查找匹配的章节
        matched = []
        for ch, cnt in level1_counter.items():
            if std_key in ch or ch in std_key:
                matched.append((ch, cnt))

        if matched:
            for ch, cnt in matched:
                coverage = f"{cnt}/16 ({cnt/16*100:.1f}%)"
                status = "✅ 常见" if cnt >= 8 else "⚠️ 较少"
                report.append(f"| {std_name} | {ch} | {coverage} | {status} |")
        else:
            report.append(f"| {std_name} | 未发现 | 0/16 (0%) | ❌ 缺失 |")

    report.append("\n### 5.2 实际文档中额外的章节（标准7章节中没有的）\n\n")

    extra_chapters = []
    for ch, cnt in level1_counter.items():
        is_standard = False
        for std_key in standard_7.keys():
            if std_key in ch or ch in std_key:
                is_standard = True
                break
        if not is_standard:
            extra_chapters.append((ch, cnt))

    report.append("| 额外章节 | 出现次数 | 覆盖率 |")
    report.append("|---|---|---|")
    for ch, cnt in sorted(extra_chapters, key=lambda x: x[1], reverse=True):
        coverage = f"{cnt}/16 ({cnt/16*100:.1f}%)"
        report.append(f"| {ch} | {cnt} | {coverage} |")

    report.append("\n## 六、特殊发现\n\n")
    report.append("### 6.1 章节编号方式多样化\n")
    report.append("- 中文数字: 一、二、三、四...\n")
    report.append("- 阿拉伯数字: 1、2、3、4... 或 1. 2. 3. 4...\n")
    report.append("- 分级编号: 1.1, 1.2, 2.1, 2.2...\n\n")

    report.append("### 6.2 章节层级深度\n")
    max_levels = []
    for doc_id, chapters in analysis['all_chapters'].items():
        levels = [lvl for lvl, _, _ in chapters]
        if levels:
            max_levels.append((doc_id, max(levels)))

    report.append(f"- 最大章节层级: {max(lvl for _, lvl in max_levels)} 级\n")
    report.append(f"- 文档平均章节数: {sum(len(ch) for ch in analysis['all_chapters'].values()) / len(analysis['all_chapters']):.1f}\n\n")

    report.append("### 6.3 安全与应急类章节突出\n")
    safety_related = [ch for ch in level1_counter.keys() if any(kw in ch for kw in ['安全', '应急', '危险', '风险', '保证'])]
    report.append(f"- 共识别到 {len(safety_related)} 个安全/应急相关章节\n")
    for ch in safety_related:
        cnt = level1_counter[ch]
        report.append(f"  - {ch} ({cnt}/16, {cnt/16*100:.1f}%)\n")

    report.append("\n## 七、标准章节结构建议\n\n")
    report.append("基于16份实际文档分析，建议的标准章节结构（包含核心章节 + 常见章节）：\n\n")

    suggested = []
    for ch, cnt in level1_counter.most_common():
        if cnt >= 6:  # 至少出现在6份文档中
            suggested.append((ch, cnt))

    for idx, (ch, cnt) in enumerate(suggested, 1):
        variants = chapter_variants[ch]
        coverage = f"{cnt}/16 ({cnt/16*100:.1f}%)"
        report.append(f"{idx}. **{ch}** - 出现频率: {coverage}\n")
        if len(variants) > 1:
            report.append(f"   - 命名变体: {', '.join(sorted(variants))}\n")

    # 写入报告
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report))

    print(f"✅ 分析报告已生成: {output_file}")


def main():
    """主函数"""
    output_dir = Path('/home/pci/smart-construction-ai/output')
    report_dir = Path('/home/pci/smart-construction-ai/.reports')
    report_dir.mkdir(exist_ok=True)

    print("开始分析16份施工方案文档的章节结构...")
    analysis = analyze_chapters(output_dir)

    print(f"✅ 分析完成，共分析 {len(analysis['all_chapters'])} 份文档")
    print(f"✅ 识别到 {len(analysis['level1_counter'])} 个不同的一级章节")

    # 生成报告
    report_file = report_dir / 'chapter_structure_analysis.md'
    generate_report(analysis, report_file)

    # 保存原始数据为JSON
    json_file = report_dir / 'chapter_analysis_data.json'
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump({
            'level1_counter': dict(analysis['level1_counter']),
            'level2_by_level1': analysis['level2_by_level1'],
            'chapter_variants': analysis['chapter_variants']
        }, f, ensure_ascii=False, indent=2)
    print(f"✅ 原始数据已保存: {json_file}")


if __name__ == '__main__':
    main()
