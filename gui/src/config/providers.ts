export type ProviderPresetOption = {
  value: string
  label: string
  models: string[]
  baseUrl: string
}

export const PROVIDER_PRESETS: ProviderPresetOption[] = [
  {
    value: 'openai',
    label: 'OpenAI',
    models: ['gpt-5.2', 'gpt-5', 'gpt-5-mini'],
    baseUrl: 'https://api.openai.com/v1',
  },
  {
    value: 'anthropic',
    label: 'Anthropic',
    models: ['claude-sonnet-4-5-20250929', 'claude-opus-4-6-20260205', 'claude-haiku-4-5-20250929'],
    baseUrl: '',
  },
  {
    value: 'openrouter',
    label: 'OpenRouter',
    models: ['openrouter/auto', 'openai/gpt-5.2', 'anthropic/claude-sonnet-4.5'],
    baseUrl: 'https://openrouter.ai/api/v1',
  },
  {
    value: 'deepseek',
    label: 'DeepSeek',
    models: ['deepseek-chat', 'deepseek-reasoner', 'deepseek-v3'],
    baseUrl: 'https://api.deepseek.com/v1',
  },
  {
    value: 'google',
    label: 'Google',
    models: ['gemini-2.5-pro', 'gemini-2.5-flash', 'gemini-2.5-flash-lite'],
    baseUrl: 'https://generativelanguage.googleapis.com/v1beta/openai',
  },
  {
    value: 'ollama',
    label: 'Ollama (local)',
    models: ['llama3.2', 'qwen2.5-coder:7b', 'mistral'],
    baseUrl: 'http://127.0.0.1:11434/v1',
  },
  {
    value: 'openai-codex',
    label: 'OpenAI Codex',
    models: ['gpt-5.3-codex', 'gpt-5.2-codex', 'gpt-5-codex'],
    baseUrl: '',
  },
]
