import { describe, it, expect, beforeEach } from 'vitest'
import { useResearchStore } from '@/store/research'
import type { ConversationMessage } from '@/types'

describe('useResearchStore - Conversation Features', () => {
  beforeEach(() => {
    useResearchStore.getState().reset()
  })

  describe('initial state', () => {
    it('has empty messages array', () => {
      const state = useResearchStore.getState()
      expect(state.messages).toEqual([])
    })
  })

  describe('addMessage', () => {
    it('adds a user message', () => {
      const message: ConversationMessage = {
        role: 'user',
        content: 'Test query',
        timestamp: '2024-01-01T00:00:00Z',
        metadata: { action: 'start_research' },
      }
      
      useResearchStore.getState().addMessage(message)
      const messages = useResearchStore.getState().messages
      
      expect(messages).toHaveLength(1)
      expect(messages[0].role).toBe('user')
      expect(messages[0].content).toBe('Test query')
    })

    it('adds an assistant message', () => {
      const message: ConversationMessage = {
        role: 'assistant',
        content: 'Generated review',
        timestamp: '2024-01-01T00:00:01Z',
        metadata: { action: 'draft_completed' },
      }
      
      useResearchStore.getState().addMessage(message)
      const messages = useResearchStore.getState().messages
      
      expect(messages).toHaveLength(1)
      expect(messages[0].role).toBe('assistant')
    })

    it('appends messages in order', () => {
      const userMessage: ConversationMessage = {
        role: 'user',
        content: 'First message',
        timestamp: '2024-01-01T00:00:00Z',
      }
      const assistantMessage: ConversationMessage = {
        role: 'assistant',
        content: 'Response',
        timestamp: '2024-01-01T00:00:01Z',
      }
      const followUpMessage: ConversationMessage = {
        role: 'user',
        content: 'Follow-up',
        timestamp: '2024-01-01T00:00:02Z',
      }
      
      useResearchStore.getState().addMessage(userMessage)
      useResearchStore.getState().addMessage(assistantMessage)
      useResearchStore.getState().addMessage(followUpMessage)
      
      const messages = useResearchStore.getState().messages
      expect(messages).toHaveLength(3)
      expect(messages[0].content).toBe('First message')
      expect(messages[1].content).toBe('Response')
      expect(messages[2].content).toBe('Follow-up')
    })
  })

  describe('setMessages', () => {
    it('replaces all messages', () => {
      useResearchStore.getState().addMessage({
        role: 'user',
        content: 'Old message',
        timestamp: '2024-01-01T00:00:00Z',
      })

      const newMessages: ConversationMessage[] = [
        { role: 'user', content: 'New message 1', timestamp: '2024-01-02T00:00:00Z' },
        { role: 'assistant', content: 'New message 2', timestamp: '2024-01-02T00:00:01Z' },
      ]
      
      useResearchStore.getState().setMessages(newMessages)
      const messages = useResearchStore.getState().messages
      
      expect(messages).toHaveLength(2)
      expect(messages[0].content).toBe('New message 1')
      expect(messages[1].content).toBe('New message 2')
    })
  })

  describe('clearMessages', () => {
    it('removes all messages', () => {
      useResearchStore.getState().addMessage({
        role: 'user',
        content: 'Message 1',
        timestamp: '2024-01-01T00:00:00Z',
      })
      useResearchStore.getState().addMessage({
        role: 'assistant',
        content: 'Message 2',
        timestamp: '2024-01-01T00:00:01Z',
      })
      
      expect(useResearchStore.getState().messages).toHaveLength(2)
      
      useResearchStore.getState().clearMessages()
      
      expect(useResearchStore.getState().messages).toEqual([])
    })
  })

  describe('reset', () => {
    it('clears messages along with other state', () => {
      useResearchStore.getState().setThreadId('test-thread')
      useResearchStore.getState().setStatus('completed')
      useResearchStore.getState().addMessage({
        role: 'user',
        content: 'Test',
        timestamp: '2024-01-01T00:00:00Z',
      })
      
      useResearchStore.getState().reset()
      
      const state = useResearchStore.getState()
      expect(state.threadId).toBeNull()
      expect(state.status).toBe('idle')
      expect(state.messages).toEqual([])
    })
  })

  describe('continuing status', () => {
    it('supports continuing status', () => {
      useResearchStore.getState().setStatus('continuing')
      expect(useResearchStore.getState().status).toBe('continuing')
    })
  })

  describe('multi-turn conversation flow', () => {
    it('simulates a complete multi-turn conversation', () => {
      useResearchStore.getState().setThreadId('thread-123')
      useResearchStore.getState().setStatus('searching')
      useResearchStore.getState().addMessage({
        role: 'user',
        content: 'Research transformer architecture',
        timestamp: '2024-01-01T10:00:00Z',
        metadata: { action: 'start_research' },
      })

      useResearchStore.getState().setStatus('completed')
      useResearchStore.getState().addMessage({
        role: 'assistant',
        content: 'Generated literature review with 5 sections',
        timestamp: '2024-01-01T10:01:00Z',
        metadata: { action: 'draft_completed' },
      })

      useResearchStore.getState().setStatus('continuing')
      useResearchStore.getState().addMessage({
        role: 'user',
        content: 'Expand the methodology section',
        timestamp: '2024-01-01T10:02:00Z',
        metadata: { action: 'continue_research' },
      })

      useResearchStore.getState().setStatus('completed')
      useResearchStore.getState().addMessage({
        role: 'assistant',
        content: 'Updated draft with expanded methodology',
        timestamp: '2024-01-01T10:03:00Z',
        metadata: { action: 'draft_updated' },
      })

      const state = useResearchStore.getState()
      expect(state.messages).toHaveLength(4)
      expect(state.messages.filter(m => m.role === 'user')).toHaveLength(2)
      expect(state.messages.filter(m => m.role === 'assistant')).toHaveLength(2)
      expect(state.status).toBe('completed')
    })
  })
})
