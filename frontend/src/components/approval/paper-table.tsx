"use client"

import { useResearchStore } from "@/store/research"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

export function PaperTable() {
  const candidatePapers = useResearchStore((s) => s.candidatePapers)
  const selectedPaperIds = useResearchStore((s) => s.selectedPaperIds)
  const togglePaperSelection = useResearchStore((s) => s.togglePaperSelection)
  const selectAllPapers = useResearchStore((s) => s.selectAllPapers)
  const deselectAllPapers = useResearchStore((s) => s.deselectAllPapers)

  const allSelected = candidatePapers.length > 0 && 
    candidatePapers.every((p) => selectedPaperIds.has(p.paper_id))
  const someSelected = candidatePapers.some((p) => selectedPaperIds.has(p.paper_id))

  const handleSelectAll = () => {
    if (allSelected) {
      deselectAllPapers()
    } else {
      selectAllPapers()
    }
  }

  return (
    <div className="max-h-[60vh] overflow-y-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-12">
              <Checkbox
                checked={allSelected}
                onCheckedChange={handleSelectAll}
                aria-label="Select all"
                {...(someSelected && !allSelected ? { "data-state": "indeterminate" } : {})}
              />
            </TableHead>
            <TableHead>Title</TableHead>
            <TableHead className="w-32">Year</TableHead>
            <TableHead className="w-48">Authors</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {candidatePapers.map((paper) => (
            <TableRow key={paper.paper_id}>
              <TableCell>
                <Checkbox
                  checked={selectedPaperIds.has(paper.paper_id)}
                  onCheckedChange={() => togglePaperSelection(paper.paper_id)}
                  aria-label={`Select ${paper.title}`}
                />
              </TableCell>
              <TableCell>
                <div className="max-w-md">
                  <p className="font-medium text-sm line-clamp-2">{paper.title}</p>
                  {paper.abstract && (
                    <p className="text-xs text-zinc-500 mt-1 line-clamp-2">
                      {paper.abstract}
                    </p>
                  )}
                </div>
              </TableCell>
              <TableCell className="text-sm text-zinc-500">
                {paper.year || "N/A"}
              </TableCell>
              <TableCell className="text-sm text-zinc-500">
                <span className="line-clamp-1">
                  {paper.authors.slice(0, 2).join(", ")}
                  {paper.authors.length > 2 && " et al."}
                </span>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
