# Design system

Talk to Data pairs an obsidian side panel with a white workspace. Silver chrome is used sparingly, on the New chat button and the brand mark, so the data stays the focus. Tokens come from two places that must stay in sync:

- `.streamlit/config.toml`: theme values Streamlit applies to its own widgets, including `[theme.sidebar]` for the dark panel.
- `app.py` `:root` block: CSS variables for the custom pieces.

## Tokens

| Token | Value | Use |
|---|---|---|
| `--tt-obsidian` | `#0a0a0b` | Side panel base, with a soft white sheen at the top right |
| `--tt-obsidian-line` | `#232327` | Dividers and outlines on the dark panel |
| `--tt-on-obsidian` / `-2` | `#e7e7ea` / `#8d8d96` | Text on the dark panel: primary and muted |
| `--tt-chrome` | silver gradient, `#fbfbfc` → `#9c9da3` → `#e9e9ec` | New chat button and brand mark only |
| `--tt-ink` | `#0a0a0b` | Main text, upload and send buttons, assistant avatar |
| `--tt-ink-2` / `-3` | `#52525b` / `#8b8b94` | Secondary text; captions and labels |
| `--tt-surface` / `-2` | `#ffffff` / `#f7f7f8` | Page; tiles, chips, user messages |
| `--tt-border` | `#e6e6ea` | Cards, chips, expanders |
| `--tt-radius` / `-lg` | `12px` / `18px` | Cards; upload zone |
| `--tt-shadow` | two soft layers | Suggestion cards, chat input |
| `--tt-space-1…6` | 4, 8, 12, 16, 24 px | Spacing scale |
| Font | Inter, then `system-ui` | All text; the hero headline is 800 weight with tight tracking |

There is no hue in the interface. Status colours come from Streamlit's own `st.error`, `st.warning` and `st.info`, and always pair with an icon.

## Chart palette

`CHART_COLORS` in `src/config.py` holds eight categorical colours, always assigned in fixed order. The palette passes colour-blind separation checks on a light surface. Three slots (aqua, yellow, magenta) fall below 3:1 contrast against white, so every chart also has its exact numbers in the "How this was calculated" table. A single-series chart uses graphite (`CHART_INK`, `#3f3f46`) to match the interface; the palette is used only when a chart has several series. One-row results are shown as metric tiles, not charts.

## Components

| Component | Built from | Notes |
|---|---|---|
| Brand mark | Inline SVG chrome bars + `.tt-brand` | Name plus "AI Data Analysis"; no external image request |
| New chat | `st.button(type="primary")` styled with `--tt-chrome` | The only primary button on screen. Reuses the current chat if it is still empty |
| Recent chats | `st.button` (`secondary` for the open chat, `tertiary` for the rest) + `.tt-when` | Newest first, with a relative time; titles truncate with an ellipsis |
| Hero | `.tt-pill`, `.tt-h1` with an SVG swoosh under "Your Data", subtitle | Empty state only |
| Upload zone | `st.file_uploader`, restyled dropzone | Dashed silver frame, black pill button, centred |
| Suggestion cards | `st.button` in 4 columns, with icons | Disabled until the chat has data |
| Chat options | `st.popover` | Rename and delete for the open chat only |
| Section label | `.tt-section` | Uppercase, muted, small |
| Data chip | `.tt-chip` | One per file: name, rows and columns |
| Messages | `st.chat_message` | Black avatars with white icons; the user message sits on a grey bubble; column capped at 980px |
| Answer | Markdown + chart or metric tiles + `.tt-meta` + expander | `$` is escaped so currency never renders as LaTeX |

## Chat behaviour

- **Scoped data:** each chat owns its files, DuckDB connection and history. The uploader is keyed per chat and only adds files; removing a file uses an explicit "Remove" button.
- **Memory:** the last 4 turns go to SQL generation as context, so follow-ups and replies to a clarifying question resolve. The answer step sees only the plain question.
- **No persistence:** chats live in the browser session only, so a refresh starts over. This is deliberate, because uploaded data is never stored.
