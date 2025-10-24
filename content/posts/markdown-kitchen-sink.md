---
title: "Markdown Kitchen Sink"
status: published
published_at: 2025-10-20T00:00:00Z
description: "A comprehensive sample exercising CommonMark + GFM features (headings, lists, code, tables, links, images, blockquotes, footnotes, tasks, etc.)."
author: "Test Fixture"
date: "2025-10-20"
tags: 
  - "test 1"
  - "election"
  - "opinion"
  - "politics"
  - "republicans"
  - "test 2"
  - "test 3"
  - "test 4"
  - "test 5"
  - "test 6"
  - "test 7"
  - "test 8"
  - "test 9"
---

# H1 — Heading Level 1
Plain paragraph text with **bold**, *italic*, ***bold italic***, and ~~strikethrough~~.
Soft line break with two spaces at end of line.  
Hard line break above used.

Inline code: `console.log("hello")` and escaped characters: \* \_ \` \# \\.

Superscript with HTML: H<sup>2</sup>O and subscript: CO<sub>2</sub>.
Highlight with HTML: <mark>important</mark>. Keyboard: <kbd>Ctrl</kbd> + <kbd>C</kbd>.

Autolink: <https://example.com>.  
Inline link: [Example](https://example.com "Example Title").  
Reference link: [Example Ref][ex-ref].  
Image (inline): ![Alt text](https://upload.wikimedia.org/wikipedia/commons/thumb/4/48/Markdown-mark.svg/120px-Markdown-mark.svg.png "Markdown Logo")  
Image (reference): ![Markdown Logo Small][img-ref]

> # Blockquote H1
> A quoted paragraph with **formatting** and a list:
> - item a
> - item b
>   - nested b1
> 
> > Nested blockquote level 2
> >
> > ```python
> > def greet(name: str) -> str:
> >     return f"Hello, {name}!"
> > ```

---

## H2 — Lists
Unordered (three marker styles are equivalent):
- dash one
- dash two
  - nested dash
* star one
+ plus one

Ordered:
1. First
2. Second
   1. Second.A
   2. Second.B
3. Third

Task list (GFM):
- [x] Completed task
- [ ] Incomplete task
  - [ ] Subtask

___

### H3 — Code Blocks
Fenced code block with language hint:

```javascript
function sum(a, b) {
  return a + b;
}
console.log(sum(2, 3));
```

Fenced code block without language:

```
$ echo "no highlighting here"
```

Inline math (common extension, may require support): $E = mc^2$.  
Block math (common extension; may require support):

```math
\int_{0}^{\pi} \sin(x)\,dx = 2
```

---

#### H4 — Tables (GFM)
| Left Align | Center Align | Right Align |
|:-----------|:------------:|------------:|
| cell `1`   | **bold**     | 123         |
| cell 2     | *italic*     | 45.6        |
| cell 3     | `code`       | 7,890       |

Footnote example with inline ref[^1] and another ref[^longnote].

---

##### H5 — Definition Lists (non‑standard; many renderers support)
Term 1
: Definition for term 1

Term 2
: First definition
: Second definition

If your renderer doesn’t support definition lists, consider using HTML:

<dl>
  <dt>HTML Term</dt>
  <dd>Definition using HTML block.</dd>
</dl>

---

###### H6 — Details/Summary (HTML block)
<details>
  <summary>Click to expand</summary>

  This content is hidden by default. It can include **Markdown** too!

  - Bullet inside details
  - Another item
</details>

Horizontal rules styles (all equivalent):
---
***
___

Anchors / heading IDs vary by renderer. You can also include a manual anchor:
<a id="custom-anchor"></a>
Jump to the [custom anchor](#custom-anchor).

Escapes and entities: &copy; &mdash; &lt; &gt; &amp;.

> Tip: Many Markdown flavors ignore raw HTML sanitization rules; behavior may vary by renderer.

<!-- HTML comment: will not be shown in most renderers -->

[^1]: This is a footnote, supported in GFM (since 2021).
[^longnote]: A longer footnote can include multiple paragraphs.

    Indented second paragraph in footnote.

[ex-ref]: https://example.com "Example Title via reference"
[img-ref]: https://upload.wikimedia.org/wikipedia/commons/thumb/4/48/Markdown-mark.svg/64px-Markdown-mark.svg.png "Markdown Logo Small"
