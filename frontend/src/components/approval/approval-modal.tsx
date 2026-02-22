"use client"

import { useResearchStore } from "@/store/research"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { PaperTable } from "./paper-table"
import { useTranslations } from 'next-intl'

interface ApprovalModalProps {
  open: boolean
  onApprove: (paperIds: string[]) => void
  onCancel?: () => void
}

export function ApprovalModal({ open, onApprove, onCancel }: ApprovalModalProps) {
  const t = useTranslations('approval')
  const candidatePapers = useResearchStore((s) => s.candidatePapers)
  const selectedPaperIds = useResearchStore((s) => s.selectedPaperIds)
  const status = useResearchStore((s) => s.status)

  const isLoading = status === "processing"
  const selectedCount = selectedPaperIds.size

  const handleApprove = () => {
    if (selectedCount > 0) {
      onApprove(Array.from(selectedPaperIds))
    }
  }

  const handleOpenChange = (isOpen: boolean) => {
    if (!isOpen && onCancel && !isLoading) {
      onCancel()
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-4xl">
        <DialogHeader>
          <DialogTitle>{t('title')}</DialogTitle>
          <DialogDescription>
            {t('description', { count: candidatePapers.length })}
          </DialogDescription>
        </DialogHeader>

        <PaperTable />

        <DialogFooter className="flex items-center justify-between sm:justify-between">
          <p className="text-sm text-zinc-500">
            {t('selected', { selected: selectedCount, total: candidatePapers.length })}
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={onCancel}
              disabled={isLoading}
            >
              {t('cancel')}
            </Button>
            <Button
              onClick={handleApprove}
              disabled={selectedCount === 0 || isLoading}
            >
              {isLoading 
                ? t('processing') 
                : t('confirm', { count: selectedCount })}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
