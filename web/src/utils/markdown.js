// 文件说明：Markdown 渲染工具，统一聊天消息中的链接与代码块展示。

import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'

const markdown = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
  typographer: false
})

const defaultLinkOpen =
  markdown.renderer.rules.link_open ||
  ((tokens, idx, options, env, self) => self.renderToken(tokens, idx, options))

markdown.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  const token = tokens[idx]
  const targetIndex = token.attrIndex('target')
  const relIndex = token.attrIndex('rel')

  if (targetIndex < 0) {
    token.attrPush(['target', '_blank'])
  } else {
    token.attrs[targetIndex][1] = '_blank'
  }

  if (relIndex < 0) {
    token.attrPush(['rel', 'noopener noreferrer'])
  } else {
    token.attrs[relIndex][1] = 'noopener noreferrer'
  }

  return defaultLinkOpen(tokens, idx, options, env, self)
}

export function renderMarkdown(content) {
  const raw = markdown.render(String(content || ''))
  return DOMPurify.sanitize(raw, {
    ADD_ATTR: ['target']
  })
}
