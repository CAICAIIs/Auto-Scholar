import io
import base64
from collections import Counter
from typing import Any

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from app.schemas import PaperMetadata


def generate_year_trend_chart(papers: list[PaperMetadata]) -> str | None:
    years = [p.year for p in papers if p.year]
    if not years:
        return None

    year_counts = Counter(years)
    sorted_years = sorted(year_counts.keys())
    counts = [year_counts[y] for y in sorted_years]

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(sorted_years, counts, color='#3b82f6', edgecolor='#1d4ed8')
    ax.set_xlabel('Year', fontsize=12)
    ax.set_ylabel('Number of Papers', fontsize=12)
    ax.set_title('Publication Year Distribution', fontsize=14, fontweight='bold')
    ax.set_xticks(sorted_years)
    ax.tick_params(axis='x', rotation=45)
    
    for i, (year, count) in enumerate(zip(sorted_years, counts)):
        ax.text(year, count + 0.1, str(count), ha='center', va='bottom', fontsize=10)

    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)

    return base64.b64encode(buf.getvalue()).decode('utf-8')


def generate_source_distribution_chart(papers: list[PaperMetadata]) -> str | None:
    if not papers:
        return None

    source_counts = Counter(p.source.value for p in papers)
    
    labels = list(source_counts.keys())
    sizes = list(source_counts.values())
    colors = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6'][:len(labels)]

    fig, ax = plt.subplots(figsize=(8, 6))
    wedges, texts, autotexts = ax.pie(
        sizes, 
        labels=labels, 
        autopct='%1.1f%%',
        colors=colors,
        startangle=90,
        explode=[0.02] * len(labels)
    )
    
    ax.set_title('Paper Sources Distribution', fontsize=14, fontweight='bold')
    
    for autotext in autotexts:
        autotext.set_fontsize(10)
        autotext.set_fontweight('bold')

    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)

    return base64.b64encode(buf.getvalue()).decode('utf-8')


def generate_author_frequency_chart(papers: list[PaperMetadata], top_n: int = 10) -> str | None:
    if not papers:
        return None

    all_authors: list[str] = []
    for p in papers:
        all_authors.extend(p.authors)

    if not all_authors:
        return None

    author_counts = Counter(all_authors)
    top_authors = author_counts.most_common(top_n)
    
    if not top_authors:
        return None

    authors = [a[0] for a in top_authors]
    counts = [a[1] for a in top_authors]

    fig, ax = plt.subplots(figsize=(10, 6))
    y_pos = range(len(authors))
    ax.barh(y_pos, counts, color='#10b981', edgecolor='#059669')
    ax.set_yticks(y_pos)
    ax.set_yticklabels(authors, fontsize=10)
    ax.invert_yaxis()
    ax.set_xlabel('Number of Papers', fontsize=12)
    ax.set_title(f'Top {len(authors)} Most Frequent Authors', fontsize=14, fontweight='bold')

    for i, count in enumerate(counts):
        ax.text(count + 0.1, i, str(count), va='center', fontsize=10)

    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)

    return base64.b64encode(buf.getvalue()).decode('utf-8')


def generate_all_charts(papers: list[PaperMetadata]) -> dict[str, str | None]:
    return {
        "year_trend": generate_year_trend_chart(papers),
        "source_distribution": generate_source_distribution_chart(papers),
        "author_frequency": generate_author_frequency_chart(papers),
    }
