<script setup lang="ts">
/**
 * Monaco Editor 组件
 * 支持 JSON / Prompt 模板编辑
 *
 * 性能优化：Monaco Editor 完全懒加载，仅在组件首次使用时加载
 */
import { computed, onMounted, shallowRef, watch } from 'vue';

import { usePreferences } from '@vben/preferences';

const props = withDefaults(defineProps<Props>(), {
  language: 'plaintext',
  height: '300px',
  readonly: false,
  placeholder: '',
  minimap: false,
  lineNumbers: true,
  wordWrap: true,
  formatOnMount: false,
});

const emit = defineEmits<{
  change: [value: string];
  mouseDown: [e: any];
  mouseUp: [e: any];
  ready: [editor: EditorInstance];
  selectionChange: [e: any];
  'update:modelValue': [value: string];
}>();

// 动态导入 Monaco Editor（约 2MB），仅在组件挂载时加载
// 使用动态 import 而非静态导入，确保代码分割
const VueMonacoEditor = shallowRef<any>(null);

// 编辑器类型定义
interface EditorInstance {
  getValue: () => string;
  setValue: (value: string) => void;
  focus: () => void;
  getModel: () => null | {
    getPositionAt: (offset: number) => { column: number; lineNumber: number };
    getValue: () => string;
  };
  getAction: (id: string) => null | { run: () => void };
  onDidChangeModelContent: (callback: () => void) => void;
  onDidChangeCursorSelection: (callback: (e: any) => void) => void;
  onMouseDown: (callback: (e: any) => void) => void;
  onMouseUp: (callback: (e: any) => void) => void;
  getSelection: () => any;
  setSelection: (selection: any) => void;
  getScrolledVisiblePosition: (position: any) => any;
  getDomNode: () => HTMLElement;
  createDecorationsCollection: (decorations: DecorationItem[]) => void;
}

interface DecorationItem {
  range: {
    endColumn: number;
    endLineNumber: number;
    startColumn: number;
    startLineNumber: number;
  };
  options: {
    hoverMessage?: { value: string };
    inlineClassName: string;
  };
}

// Props 定义
interface Props {
  modelValue: string;
  language?: 'json' | 'markdown' | 'plaintext' | 'prompt';
  height?: number | string;
  readonly?: boolean;
  placeholder?: string;
  minimap?: boolean;
  lineNumbers?: boolean;
  wordWrap?: boolean;
  formatOnMount?: boolean;
}

// 获取主题偏好
const { isDark } = usePreferences();

// 编辑器实例
const editorRef = shallowRef<EditorInstance>();
const decorationCollection = shallowRef<any>(null);
const isLoading = shallowRef(false);
const isReady = shallowRef(false);

// 计算编辑器主题
const editorTheme = computed(() => (isDark.value ? 'vs-dark' : 'vs'));

// 计算高度
const editorHeight = computed(() => {
  if (typeof props.height === 'number') {
    return `${props.height}px`;
  }
  return props.height;
});

// 实际使用的语言（prompt 映射为 plaintext）
const actualLanguage = computed(() => {
  if (props.language === 'prompt') {
    return 'plaintext';
  }
  return props.language;
});

// 编辑器配置
const editorOptions = computed(() => ({
  readOnly: props.readonly,
  minimap: { enabled: props.minimap },
  lineNumbers: (props.lineNumbers ? 'on' : 'off') as 'off' | 'on',
  wordWrap: (props.wordWrap ? 'on' : 'off') as 'off' | 'on',
  scrollBeyondLastLine: false,
  automaticLayout: true,
  fontSize: 13,
  lineHeight: 20,
  padding: { top: 12, bottom: 12 },
  renderLineHighlight: 'line' as const,
  cursorBlinking: 'smooth' as const,
  cursorSmoothCaretAnimation: 'on' as const,
  smoothScrolling: true,
  folding: true,
  foldingHighlight: true,
  showFoldingControls: 'mouseover' as const,
  bracketPairColorization: { enabled: true },
  guides: {
    bracketPairs: true,
    indentation: true,
  },
  suggest: {
    showWords: false,
  },
  quickSuggestions: props.language === 'json',
  formatOnPaste: props.language === 'json',
  tabSize: 2,
  detectIndentation: false,
  unicodeHighlight: {
    ambiguousCharacters: false,
    invisibleCharacters: false,
  },
  // hover 配置：始终在下方显示，避免第一行 hover 被遮挡
  hover: {
    above: false,
    delay: 300,
  },
}));

// 处理值变化
function handleChange(value: string | undefined = '') {
  emit('update:modelValue', value);
  emit('change', value);
}

// 编辑器挂载回调
function handleEditorMount(editor: EditorInstance) {
  editorRef.value = editor;
  isReady.value = true;
  isLoading.value = false;

  // 如果是 JSON 且需要格式化
  if (props.formatOnMount && props.language === 'json' && props.modelValue) {
    setTimeout(() => {
      formatDocument();
    }, 100);
  }

  // 注册 Prompt 模板变量高亮
  if (props.language === 'prompt') {
    registerPromptDecorations(editor);
  }

  // 监听选择变化
  editor.onDidChangeCursorSelection((e) => {
    emit('selectionChange', e);
  });

  // 监听鼠标按下
  editor.onMouseDown((e) => {
    emit('mouseDown', e);
  });

  // 监听鼠标抬起
  editor.onMouseUp((e) => {
    emit('mouseUp', e);
  });

  emit('ready', editor);
}

// 格式化 JSON
function formatDocument() {
  if (editorRef.value && props.language === 'json') {
    editorRef.value.getAction('editor.action.formatDocument')?.run();
  }
}

// Prompt 模板变量高亮
function registerPromptDecorations(editor: EditorInstance) {
  const updateDecorations = () => {
    const model = editor.getModel();
    if (!model) return;

    const text = model.getValue();
    const decorations: DecorationItem[] = [];

    // 匹配 {{变量名}} 模式
    const regex = /\{\{[\s\S]*?\}\}/g;
    let match = regex.exec(text);

    while (match !== null) {
      const startPos = model.getPositionAt(match.index);
      const endPos = model.getPositionAt(match.index + match[0].length);

      decorations.push({
        range: {
          startLineNumber: startPos.lineNumber,
          startColumn: startPos.column,
          endLineNumber: endPos.lineNumber,
          endColumn: endPos.column,
        },
        options: {
          inlineClassName: 'monaco-prompt-variable',
          hoverMessage: { value: `变量: ${match[0]}` },
        },
      });
      match = regex.exec(text);
    }

    editor.createDecorationsCollection(decorations);
  };

  // 初始化和内容变化时更新高亮
  updateDecorations();
  editor.onDidChangeModelContent(updateDecorations);
}

// 加载 Monaco Editor 组件
async function loadMonaco() {
  if (VueMonacoEditor.value) return;

  isLoading.value = true;
  try {
    // 使用 CDN 方式配置 Monaco Editor（避免 worker 打包问题）
    const { loader } = await import('@guolao/vue-monaco-editor');

    loader.config({
      paths: {
        vs: 'https://cdn.jsdelivr.net/npm/monaco-editor@0.55.1/min/vs',
      },
    });

    // 动态导入 Vue Monaco Editor 组件
    const module = await import('@guolao/vue-monaco-editor');
    VueMonacoEditor.value = module.Editor;
  } catch (error) {
    console.error('Failed to load Monaco Editor:', error);
    isLoading.value = false;
  }
}

// 监听主题变化
watch(isDark, () => {
  // 主题会自动通过 computed 更新
});

// 暴露方法
defineExpose({
  getEditor: () => editorRef.value,
  formatDocument,
  getValue: () => editorRef.value?.getValue() ?? '',
  setValue: (value: string) => editorRef.value?.setValue(value),
  focus: () => editorRef.value?.focus(),
  setDecorations: (decorations: DecorationItem[]) => {
    const editor = editorRef.value;
    if (!editor) return;

    if (decorationCollection.value) {
      decorationCollection.value.set(decorations);
    } else {
      decorationCollection.value =
        editor.createDecorationsCollection(decorations);
    }
  },
  clearSelection: () => {
    const editor = editorRef.value;
    if (!editor) return;
    const selection = editor.getSelection();
    if (selection) {
      editor.setSelection({
        startLineNumber: selection.startLineNumber,
        startColumn: selection.startColumn,
        endLineNumber: selection.startLineNumber,
        endColumn: selection.startColumn,
      });
    }
  },
});

onMounted(() => {
  // 添加自定义 CSS 样式
  const style = document.createElement('style');
  style.textContent = `
    .monaco-prompt-variable {
      background-color: rgba(var(--primary-rgb), 0.15);
      border-radius: 3px;
      padding: 0 2px;
      color: hsl(var(--primary));
      font-weight: 500;
    }
  `;
  document.head.append(style);

  // 延迟加载 Monaco Editor
  loadMonaco();
});
</script>

<template>
  <div class="monaco-editor-container" :style="{ height: editorHeight }">
    <!-- 加载占位符 -->
    <div v-if="isLoading" class="monaco-loading">
      <span>编辑器加载中...</span>
    </div>

    <!-- Monaco Editor (动态加载) -->
    <component
      :is="VueMonacoEditor"
      v-if="VueMonacoEditor"
      :value="modelValue"
      :language="actualLanguage"
      :theme="editorTheme"
      :options="editorOptions"
      :height="editorHeight"
      @change="handleChange"
      @mount="handleEditorMount"
    />

    <!-- 初始占位符 -->
    <div
      v-if="!modelValue && placeholder && !isReady"
      class="monaco-placeholder"
    >
      {{ placeholder }}
    </div>
  </div>
</template>

<style scoped>
.monaco-editor-container {
  position: relative;
  overflow: hidden;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 6px;
}

.monaco-editor-container:focus-within {
  border-color: hsl(var(--primary));
  box-shadow: 0 0 0 2px hsl(var(--primary) / 10%);
}

.monaco-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  font-size: 13px;
  color: hsl(var(--muted-foreground));
}

.monaco-placeholder {
  position: absolute;
  top: 12px;
  left: 52px;
  font-size: 13px;
  color: hsl(var(--muted-foreground));
  pointer-events: none;
  user-select: none;
}

:deep(.monaco-editor) {
  border-radius: 6px;
}

:deep(.monaco-editor .margin) {
  background: transparent !important;
}

/* 调整 hover 显示样式，确保内容可见 */
:deep(.monaco-hover) {
  z-index: 9999 !important;
}

:deep(.monaco-hover-content) {
  max-width: 400px;
  max-height: 300px;
  overflow: auto;
  word-break: normal;
  overflow-wrap: break-word;
  white-space: pre-wrap;
}
</style>
