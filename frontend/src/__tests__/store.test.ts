import { describe, it, expect, beforeEach } from 'vitest'
import { useResearchStore } from '@/store/research'
import type { Paper, DraftOutput } from '@/types'

describe('useResearchStore', () => {
  beforeEach(() => {
    useResearchStore.getState().reset()
  })

  describe('initial state', () => {
    it('has correct default values', () => {
      const state = useResearchStore.getState()
      expect(state.threadId).toBeNull()
      expect(state.status).toBe('idle')
      expect(state.logs).toEqual([])
      expect(state.candidatePapers).toEqual([])
      expect(state.approvedPapers).toEqual([])
      expect(state.draft).toBeNull()
      expect(state.outputLanguage).toBe('en')
      expect(state.searchSources).toEqual(['semantic_scholar', 'arxiv', 'pubmed'])
    })
  })

  describe('setThreadId', () => {
    it('sets thread id', () => {
      useResearchStore.getState().setThreadId('test-123')
      expect(useResearchStore.getState().threadId).toBe('test-123')
    })

    it('clears thread id with null', () => {
      useResearchStore.getState().setThreadId('test-123')
      useResearchStore.getState().setThreadId(null)
      expect(useResearchStore.getState().threadId).toBeNull()
    })
  })

  describe('setStatus', () => {
    it('updates workflow status', () => {
      useResearchStore.getState().setStatus('searching')
      expect(useResearchStore.getState().status).toBe('searching')

      useResearchStore.getState().setStatus('completed')
      expect(useResearchStore.getState().status).toBe('completed')
    })
  })

  describe('logs', () => {
    it('adds log entries with timestamp', () => {
      useResearchStore.getState().addLog('system', 'Test message')
      const logs = useResearchStore.getState().logs
      expect(logs).toHaveLength(1)
      expect(logs[0].node).toBe('system')
      expect(logs[0].message).toBe('Test message')
      expect(logs[0].timestamp).toBeInstanceOf(Date)
    })

    it('clears logs', () => {
      useResearchStore.getState().addLog('system', 'Message 1')
      useResearchStore.getState().addLog('system', 'Message 2')
      useResearchStore.getState().clearLogs()
      expect(useResearchStore.getState().logs).toEqual([])
    })
  })

  describe('paper selection', () => {
    const mockPapers: Paper[] = [
      { paper_id: 'p1', title: 'Paper 1', authors: [], abstract: '', url: '', year: 2023, doi: null, pdf_url: null, is_approved: false, core_contribution: null, structured_contribution: null },
      { paper_id: 'p2', title: 'Paper 2', authors: [], abstract: '', url: '', year: 2024, doi: null, pdf_url: null, is_approved: false, core_contribution: null, structured_contribution: null },
      { paper_id: 'p3', title: 'Paper 3', authors: [], abstract: '', url: '', year: 2024, doi: null, pdf_url: null, is_approved: false, core_contribution: null, structured_contribution: null },
    ]

    it('sets candidate papers and selects all by default', () => {
      useResearchStore.getState().setCandidatePapers(mockPapers)
      const state = useResearchStore.getState()
      expect(state.candidatePapers).toHaveLength(3)
      expect(state.selectedPaperIds.size).toBe(3)
      expect(state.selectedPaperIds.has('p1')).toBe(true)
      expect(state.selectedPaperIds.has('p2')).toBe(true)
      expect(state.selectedPaperIds.has('p3')).toBe(true)
    })

    it('toggles paper selection', () => {
      useResearchStore.getState().setCandidatePapers(mockPapers)
      useResearchStore.getState().togglePaperSelection('p1')
      expect(useResearchStore.getState().selectedPaperIds.has('p1')).toBe(false)
      
      useResearchStore.getState().togglePaperSelection('p1')
      expect(useResearchStore.getState().selectedPaperIds.has('p1')).toBe(true)
    })

    it('selects all papers', () => {
      useResearchStore.getState().setCandidatePapers(mockPapers)
      useResearchStore.getState().deselectAllPapers()
      useResearchStore.getState().selectAllPapers()
      expect(useResearchStore.getState().selectedPaperIds.size).toBe(3)
    })

    it('deselects all papers', () => {
      useResearchStore.getState().setCandidatePapers(mockPapers)
      useResearchStore.getState().deselectAllPapers()
      expect(useResearchStore.getState().selectedPaperIds.size).toBe(0)
    })
  })

  describe('draft editing', () => {
    const mockDraft: DraftOutput = {
      title: 'Test Review',
      sections: [
        { heading: 'Introduction', content: 'Intro content [1]', cited_paper_ids: ['p1'] },
        { heading: 'Methods', content: 'Methods content [2]', cited_paper_ids: ['p2'] },
      ],
    }

    it('sets draft and creates editable copy', () => {
      useResearchStore.getState().setDraft(mockDraft)
      const state = useResearchStore.getState()
      expect(state.draft).toEqual(mockDraft)
      expect(state.editedDraft).toEqual(mockDraft)
      expect(state.editedDraft).not.toBe(state.draft)
    })

    it('updates section content in edited draft', () => {
      useResearchStore.getState().setDraft(mockDraft)
      useResearchStore.getState().updateSectionContent(0, 'Updated intro')
      
      const state = useResearchStore.getState()
      expect(state.editedDraft?.sections[0].content).toBe('Updated intro')
      expect(state.draft?.sections[0].content).toBe('Intro content [1]')
    })

    it('resets to original draft', () => {
      useResearchStore.getState().setDraft(mockDraft)
      useResearchStore.getState().updateSectionContent(0, 'Modified')
      useResearchStore.getState().resetToOriginal()
      
      expect(useResearchStore.getState().editedDraft?.sections[0].content).toBe('Intro content [1]')
    })

    it('getExportDraft returns edited draft if available', () => {
      useResearchStore.getState().setDraft(mockDraft)
      useResearchStore.getState().updateSectionContent(0, 'Export this')
      
      const exportDraft = useResearchStore.getState().getExportDraft()
      expect(exportDraft?.sections[0].content).toBe('Export this')
    })
  })

  describe('output language', () => {
    it('sets output language', () => {
      useResearchStore.getState().setOutputLanguage('zh')
      expect(useResearchStore.getState().outputLanguage).toBe('zh')
      
      useResearchStore.getState().setOutputLanguage('en')
      expect(useResearchStore.getState().outputLanguage).toBe('en')
    })
  })

  describe('search sources', () => {
    it('sets search sources', () => {
      useResearchStore.getState().setSearchSources(['arxiv', 'pubmed'])
      expect(useResearchStore.getState().searchSources).toEqual(['arxiv', 'pubmed'])
    })

    it('toggles search source on', () => {
      useResearchStore.getState().setSearchSources(['semantic_scholar'])
      useResearchStore.getState().toggleSearchSource('arxiv')
      expect(useResearchStore.getState().searchSources).toContain('arxiv')
      expect(useResearchStore.getState().searchSources).toContain('semantic_scholar')
    })

    it('toggles search source off', () => {
      useResearchStore.getState().setSearchSources(['semantic_scholar', 'arxiv'])
      useResearchStore.getState().toggleSearchSource('arxiv')
      expect(useResearchStore.getState().searchSources).not.toContain('arxiv')
      expect(useResearchStore.getState().searchSources).toContain('semantic_scholar')
    })

    it('prevents removing last source', () => {
      useResearchStore.getState().setSearchSources(['semantic_scholar'])
      useResearchStore.getState().toggleSearchSource('semantic_scholar')
      expect(useResearchStore.getState().searchSources).toEqual(['semantic_scholar'])
    })
  })

  describe('error handling', () => {
    it('sets error and updates status', () => {
      useResearchStore.getState().setError('Something went wrong')
      const state = useResearchStore.getState()
      expect(state.error).toBe('Something went wrong')
      expect(state.status).toBe('error')
    })

    it('clears error', () => {
      useResearchStore.getState().setStatus('searching')
      useResearchStore.getState().setError('Error')
      useResearchStore.getState().setError(null)
      expect(useResearchStore.getState().error).toBeNull()
    })
  })

  describe('reset', () => {
    it('resets all state to initial values', () => {
      useResearchStore.getState().setThreadId('test')
      useResearchStore.getState().setStatus('completed')
      useResearchStore.getState().addLog('system', 'test')
      useResearchStore.getState().setOutputLanguage('zh')
      useResearchStore.getState().setSearchSources(['arxiv'])
      
      useResearchStore.getState().reset()
      
      const state = useResearchStore.getState()
      expect(state.threadId).toBeNull()
      expect(state.status).toBe('idle')
      expect(state.logs).toEqual([])
      expect(state.outputLanguage).toBe('en')
      expect(state.searchSources).toEqual(['semantic_scholar', 'arxiv', 'pubmed'])
    })
  })
})
