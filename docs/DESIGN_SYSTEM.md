# Design system

Talk to Data uses a quiet, neutral look so the data is the loudest thing on the page. Tokens come from two places that must stay in sync:

- `.streamlit/config.toml`: theme values Streamlit applies to its own widgets.
- `app.py` `:root` block: CSS variables for the custom pieces.

## Tokens

| Token | Value | Use |
|---|---|---|
| `--tt-ink` | `#18181b` | Primary text, titles |
| `--tt-ink-2` | `#52525b` | Secondary text |
| `--tt-ink-3` | `#8b8b94` | Captions, section labels, answer meta |
| `--tt-surface` | `#ffffff` | Page |
| `--tt-surface-2` | `#f6f6f8` | Sidebar, metric tiles |
| `--tt-border` | `#e4e4e7` | Dividers, chips, tiles |
| `--tt-accent` | `#2a78d6` | Primary action (New chat), focus, chart slot 1 |
| `--tt-radius` | `10px` | Tiles and panels |
| `--tt-space-1…6` | 4, 8, 12, 16, 24 px | Spacing scale |
| Font | Inter, then `system-ui` | All text |

The only saturated colour in the interface is the accent. Status colours come from Streamlit's own `st.error`, `st.warning` and `st.info`, and always pair with an icon.

## Chart palette

`CHART_COLORS` in `src/config.py` holds eight categorical colours, always assigned in fixed order. The palette passes colour-blind separation checks on a light surface. Three slots (aqua, yellow, magenta) fall below 3:1 contrast against white, so every chart also has its exact numbers in the "How this was calculated" table. A single-series chart uses slot 1 only. One-row results are shown as metric tiles, not charts.

## Components

| Component | Built from | Notes |
|---|---|---|
| Brand mark | Inline SVG + `.tt-brand` | No external image request |
| New chat | `st.button(type="primary")` | The only primary button on screen. Reuses the current chat if it is still empty |
| Chat list | `st.button`: `secondary` for the open chat, `tertiary` for the rest | Newest first; titles truncate with an ellipsis |
| Chat options | `st.popover` | Rename and delete for the open chat only |
| Section label | `.tt-section` | Uppercase, muted, small |
| Data chip | `.tt-chip` | One per file: name, rows and columns |
| Messages | `st.chat_message` | `person` and `analytics` icons; a readable column capped at 880px |
| Answer | Markdown + chart or metric tiles + `.tt-meta` + expander | `$` is escaped so currency never renders as LaTeX |
| Empty state | `.tt-empty` + uploader | Shown in a chat with no data and no messages |

## Chat behaviour

- **Scoped data:** each chat owns its files, DuckDB connection and history. The uploader is keyed per chat and only adds files; removing a file uses an explicit "Remove" button.
- **Memory:** the last 4 turns go to SQL generation as context, so follow-ups and replies to a clarifying question resolve. The answer step sees only the plain question.
- **No persistence:** chats live in the browser session only, so a refresh starts over. This is deliberate, because uploaded data is never stored.
