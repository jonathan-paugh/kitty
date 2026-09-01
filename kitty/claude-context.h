/*
 * Claude Code context breakdown filter.
 *
 * Self-contained, and deliberately so: this is a private feature for one program's output,
 * not general terminal behaviour. Everything it does lives in claude-context.c, and the rest
 * of kitty touches it only through the two calls below plus a handful of one-line hooks:
 *
 *   screen.c   two calls to the functions declared here, and the Screen member/method table
 *              entries that expose claude_orch_tokens and the render hook to Python
 *   screen.h   the claude_orch_tokens field on Screen
 *   state.h    the claude_context_breakdown option field
 *   options/definition.py   the option itself (the parse/types/to-c files are generated)
 *   window.py  mirrors the claude_orch_tokens_raw user variable into the Screen field,
 *              via kitty/claude_context.py
 *
 * Removing the feature is deleting this pair of files, kitty/claude_context.py,
 * kitty_tests/claude_context.py, and those hooks. Nothing else depends on it.
 *
 * Both entry points are no-ops unless the option is on AND the window carries a non-zero
 * orchestrator token count, so an ordinary terminal never enters the scanning code.
 */
#pragma once

#include "screen.h"

// Rewrites the row at y if it is one of the two rows the filter owns. Called as a row is
// evicted into history, which for this output is the only trigger that reliably sees it.
void screen_annotate_claude_context_row(Screen *self, index_type y);

// Same, across every dirty row. Called from render prep, before the dirty flags are consumed.
void screen_annotate_claude_context_dirty_rows(Screen *self);
