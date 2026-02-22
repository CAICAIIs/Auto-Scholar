import { create } from "zustand"
import type { Paper, DraftOutput, PaperSource, ConversationMessage } from "@/types"

export type WorkflowStatus = 
  | "idle" 
  | "searching" 
  | "waiting_approval" 
  | "processing" 
  | "drafting" 
  | "continuing"
  | "completed" 
  | "error"

export type ProcessingStage = "extracting" | "drafting" | "qa"

export type PaperProcessingStatus = "pending" | "processing" | "completed" | "failed"

interface PaperProcessingState {
  paperId: string
  status: PaperProcessingStatus
  message?: string
}

interface LogEntry {
  timestamp: Date
  node: string
  message: string
}

interface ResearchState {
  threadId: string | null
  status: WorkflowStatus
  logs: LogEntry[]
  candidatePapers: Paper[]
  selectedPaperIds: Set<string>
  approvedPapers: Paper[]
  draft: DraftOutput | null
  editedDraft: DraftOutput | null
  isEditing: boolean
  error: string | null
  outputLanguage: "en" | "zh"
  searchSources: PaperSource[]
  messages: ConversationMessage[]
  
  processingStage: ProcessingStage | null
  paperProcessingStates: Map<string, PaperProcessingState>
  processingStartTime: number | null
  
  setThreadId: (id: string | null) => void
  setStatus: (status: WorkflowStatus) => void
  addLog: (node: string, message: string) => void
  clearLogs: () => void
  setCandidatePapers: (papers: Paper[]) => void
  togglePaperSelection: (paperId: string) => void
  selectAllPapers: () => void
  deselectAllPapers: () => void
  setApprovedPapers: (papers: Paper[]) => void
  setDraft: (draft: DraftOutput | null) => void
  setEditedDraft: (draft: DraftOutput | null) => void
  updateSectionContent: (sectionIndex: number, content: string) => void
  setIsEditing: (editing: boolean) => void
  resetToOriginal: () => void
  getExportDraft: () => DraftOutput | null
  setError: (error: string | null) => void
  setOutputLanguage: (lang: "en" | "zh") => void
  setSearchSources: (sources: PaperSource[]) => void
  toggleSearchSource: (source: PaperSource) => void
  addMessage: (message: ConversationMessage) => void
  setMessages: (messages: ConversationMessage[]) => void
  clearMessages: () => void
  
  setProcessingStage: (stage: ProcessingStage | null) => void
  updatePaperProcessingState: (paperId: string, status: PaperProcessingStatus, message?: string) => void
  initProcessingStates: (paperIds: string[]) => void
  startProcessingSimulation: () => void
  clearProcessingStates: () => void
  
  reset: () => void
}

const initialState = {
  threadId: null,
  status: "idle" as WorkflowStatus,
  logs: [] as LogEntry[],
  candidatePapers: [] as Paper[],
  selectedPaperIds: new Set<string>(),
  approvedPapers: [] as Paper[],
  draft: null,
  editedDraft: null,
  isEditing: false,
  error: null,
  outputLanguage: "en" as const,
  searchSources: ["semantic_scholar"] as PaperSource[],
  messages: [] as ConversationMessage[],
  processingStage: null as ProcessingStage | null,
  paperProcessingStates: new Map<string, PaperProcessingState>(),
  processingStartTime: null as number | null,
}

export const useResearchStore = create<ResearchState>((set, get) => ({
  ...initialState,

  setThreadId: (id) => set({ threadId: id }),

  setStatus: (status) => set({ status }),

  addLog: (node, message) => set((state) => ({
    logs: [...state.logs, { timestamp: new Date(), node, message }]
  })),

  clearLogs: () => set({ logs: [] }),

  setCandidatePapers: (papers) => set({
    candidatePapers: papers,
    selectedPaperIds: new Set(papers.map(p => p.paper_id))
  }),

  togglePaperSelection: (paperId) => set((state) => {
    const newSet = new Set(state.selectedPaperIds)
    if (newSet.has(paperId)) {
      newSet.delete(paperId)
    } else {
      newSet.add(paperId)
    }
    return { selectedPaperIds: newSet }
  }),

  selectAllPapers: () => set((state) => ({
    selectedPaperIds: new Set(state.candidatePapers.map(p => p.paper_id))
  })),

  deselectAllPapers: () => set({ selectedPaperIds: new Set() }),

  setApprovedPapers: (papers) => set({ approvedPapers: papers }),

  setDraft: (draft) => set({ draft, editedDraft: draft ? structuredClone(draft) : null }),

  setEditedDraft: (draft) => set({ editedDraft: draft }),

  updateSectionContent: (sectionIndex, content) => set((state) => {
    if (!state.editedDraft) return state
    const newDraft = structuredClone(state.editedDraft)
    if (newDraft.sections[sectionIndex]) {
      newDraft.sections[sectionIndex].content = content
    }
    return { editedDraft: newDraft }
  }),

  setIsEditing: (editing) => set({ isEditing: editing }),

  resetToOriginal: () => set((state) => ({
    editedDraft: state.draft ? structuredClone(state.draft) : null
  })),

  getExportDraft: () => {
    const state = get()
    return state.editedDraft || state.draft
  },

  setError: (error) => set({ error, status: error ? "error" : get().status }),

  setOutputLanguage: (lang) => set({ outputLanguage: lang }),

  setSearchSources: (sources) => set({ searchSources: sources }),

  toggleSearchSource: (source) => set((state) => {
    const current = state.searchSources
    if (current.includes(source)) {
      if (current.length === 1) return state
      return { searchSources: current.filter(s => s !== source) }
    }
    return { searchSources: [...current, source] }
  }),

  addMessage: (message) => set((state) => ({
    messages: [...state.messages, message]
  })),

  setMessages: (messages) => set({ messages }),

  clearMessages: () => set({ messages: [] }),

  setProcessingStage: (stage) => set({ processingStage: stage }),

  updatePaperProcessingState: (paperId, status, message) => set((state) => {
    const newStates = new Map(state.paperProcessingStates)
    newStates.set(paperId, { paperId, status, message })
    return { paperProcessingStates: newStates }
  }),

  initProcessingStates: (paperIds) => set(() => {
    const states = new Map<string, PaperProcessingState>()
    paperIds.forEach(id => {
      states.set(id, { paperId: id, status: "pending" })
    })
    return { 
      paperProcessingStates: states,
      processingStage: "extracting",
      processingStartTime: Date.now(),
    }
  }),

  startProcessingSimulation: () => {
    const state = get()
    const paperIds = Array.from(state.selectedPaperIds)
    if (paperIds.length === 0) return

    state.initProcessingStates(paperIds)
    
    const avgTimePerPaper = 3000
    const draftTime = 5000
    const qaTime = 2000
    
    paperIds.forEach((paperId, index) => {
      const startDelay = index * avgTimePerPaper * 0.3
      const processingTime = avgTimePerPaper * (0.7 + Math.random() * 0.6)
      
      setTimeout(() => {
        const currentState = get()
        if (currentState.status !== "processing") return
        set({ processingStage: "extracting" })
        currentState.updatePaperProcessingState(paperId, "processing", "Extracting contribution...")
      }, startDelay)
      
      setTimeout(() => {
        const currentState = get()
        if (currentState.status !== "processing") return
        currentState.updatePaperProcessingState(paperId, "completed", "Done")
      }, startDelay + processingTime)
    })
    
    const totalExtractTime = paperIds.length * avgTimePerPaper * 0.5
    setTimeout(() => {
      const currentState = get()
      if (currentState.status !== "processing") return
      set({ processingStage: "drafting" })
    }, totalExtractTime)
    
    setTimeout(() => {
      const currentState = get()
      if (currentState.status !== "processing") return
      set({ processingStage: "qa" })
    }, totalExtractTime + draftTime)
  },

  clearProcessingStates: () => set({
    paperProcessingStates: new Map(),
    processingStage: null,
    processingStartTime: null,
  }),

  reset: () => set(initialState),
}))
