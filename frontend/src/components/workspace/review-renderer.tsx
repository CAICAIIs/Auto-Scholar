"use client"

import React from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import type { Paper, DraftOutput } from "@/types"
import { CitationTooltip } from "./citation-tooltip"
import { useResearchStore } from "@/store/research"
import { useTranslations } from 'next-intl'

interface ReviewRendererProps {
  draft: DraftOutput
  papers: Paper[]
  isEditing?: boolean
}

export function ReviewRenderer({ draft, papers, isEditing = false }: ReviewRendererProps) {
  const t = useTranslations('workspace')
  const updateSectionContent = useResearchStore((s) => s.updateSectionContent)
  
  const indexToPaperId = new Map<number, string>()
  papers.forEach((p, i) => indexToPaperId.set(i + 1, p.paper_id))

  const processCitationsInText = (text: string, keyPrefix: string): React.ReactNode[] => {
    const citationPattern = /\[(\d+)\]/g
    const parts: React.ReactNode[] = []
    let lastIndex = 0
    let match

    while ((match = citationPattern.exec(text)) !== null) {
      if (match.index > lastIndex) {
        parts.push(text.slice(lastIndex, match.index))
      }

      const citationNum = parseInt(match[1], 10)
      const paperId = indexToPaperId.get(citationNum)

      if (paperId) {
        parts.push(
          <CitationTooltip key={`${keyPrefix}-${match.index}-${citationNum}`} citationId={paperId} papers={papers}>
            [{citationNum}]
          </CitationTooltip>
        )
      } else {
        parts.push(match[0])
      }

      lastIndex = match.index + match[0].length
    }

    if (lastIndex < text.length) {
      parts.push(text.slice(lastIndex))
    }

    return parts
  }

  const processChildren = (children: React.ReactNode, keyPrefix: string): React.ReactNode => {
    if (typeof children === "string") {
      return <>{processCitationsInText(children, keyPrefix)}</>
    }

    if (Array.isArray(children)) {
      return (
        <>
          {children.map((child, i) => (
            <React.Fragment key={`${keyPrefix}-arr-${i}`}>
              {processChildren(child, `${keyPrefix}-${i}`)}
            </React.Fragment>
          ))}
        </>
      )
    }

    if (React.isValidElement(children)) {
      const element = children as React.ReactElement<{ children?: React.ReactNode }>
      if (element.props.children) {
        return React.cloneElement(element, {
          ...element.props,
          children: processChildren(element.props.children, `${keyPrefix}-el`),
        })
      }
    }

    return children
  }

  return (
    <article className="prose prose-zinc dark:prose-invert max-w-none">
      <h1 className="text-2xl font-bold mb-6">{draft.title}</h1>
      {draft.sections.map((section, idx) => (
        <section key={idx} className="mb-8">
          <h2 className="text-xl font-semibold mb-3">{section.heading}</h2>
          {isEditing ? (
            <textarea
              value={section.content}
              onChange={(e) => updateSectionContent(idx, e.target.value)}
              className="w-full min-h-[200px] p-3 rounded-md border border-zinc-300 dark:border-zinc-600 bg-zinc-50 dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 font-mono text-sm resize-y focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="Enter content..."
            />
          ) : (
            <div className="text-zinc-700 dark:text-zinc-300 leading-relaxed">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  p: ({ children }) => (
                    <p>{processChildren(children, `sec-${idx}`)}</p>
                  ),
                  li: ({ children }) => (
                    <li>{processChildren(children, `sec-${idx}-li`)}</li>
                  ),
                  strong: ({ children }) => (
                    <strong>{processChildren(children, `sec-${idx}-strong`)}</strong>
                  ),
                  em: ({ children }) => (
                    <em>{processChildren(children, `sec-${idx}-em`)}</em>
                  ),
                }}
              >
                {section.content}
              </ReactMarkdown>
            </div>
          )}
        </section>
      ))}

      {papers.length > 0 && (
        <section className="mt-10 pt-6 border-t border-zinc-200 dark:border-zinc-700">
          <h2 className="text-xl font-semibold mb-4">{t('references')}</h2>
          <ol className="list-decimal list-inside space-y-2 text-sm">
            {papers.map((paper) => (
              <li key={paper.paper_id} className="text-zinc-600 dark:text-zinc-400">
                <span className="text-zinc-900 dark:text-zinc-100">{paper.title}</span>
                {" - "}
                {paper.authors.slice(0, 3).join(", ")}
                {paper.authors.length > 3 && " et al."}
                {paper.year && ` (${paper.year})`}
                {paper.url && (
                  <>
                    {" "}
                    <a
                      href={paper.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-blue-500 hover:underline"
                    >
                      [link]
                    </a>
                  </>
                )}
              </li>
            ))}
          </ol>
        </section>
      )}
    </article>
  )
}
