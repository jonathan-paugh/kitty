/*
 * Claude Code context breakdown filter. See claude-context.h for how it attaches to kitty
 * and what removing it involves.
 */

#include "data-types.h"
#include "screen.h"
#include "state.h"
#include "lineops.h"
#include "line.h"
#include "claude-context.h"

// Claude Code's /context report folds the appended orchestrator layer silently into its
// "System prompt:" figure, so that row reads as Claude Code's own overhead when most of it
// is ours. This rewrites the block to separate the two: the decorative "Estimated usage by
// category" header becomes a line naming the layer's size, and the System prompt row is
// reduced to what remains once the layer is taken out.
// Operates on the reassembled grid row rather than the byte stream, so chunk boundaries,
// SGR interleaving and character widths have all been resolved by the parser already.
// Every condition below is a refusal: anything unexpected leaves the row untouched,
// because a wrong match writes cells into real program output.

#define CLAUDE_CONTEXT_BULLET 0x26c1u  // U+26C1 WHITE DRAUGHTS KING, the row's leading glyph
#define CLAUDE_CONTEXT_MAX_COLUMNS 1024u
#define CLAUDE_CONTEXT_MAX_TEXT 64u
// Stands in for any cell the filter refuses to reason about (a multicell cell, or one
// holding more than one codepoint). No real codepoint can collide with it, so the
// predicate needs no parallel array of flags to spot them.
#define CLAUDE_CONTEXT_OPAQUE 0x7fffffffu

static const char claude_context_label[] = " System prompt:";
static const char claude_context_header[] = "Estimated usage by category";
static const char claude_context_header_prefix[] = "Orchestrator layer: ";
static const char claude_context_units[] = " tokens (";

/**
 * A parsed "System prompt:" row: where its value and percentage sit, and what they say.
 */
typedef struct ClaudeContextPromptRow {
    index_type value_x;
    index_type last_non_blank;
    uint32_t tokens;
    uint32_t percent_tenths;
    bool matched;
} ClaudeContextPromptRow;

static bool
claude_context_is_blank(char_type codepoint) {
    return codepoint == 0 || codepoint == ' ';
}

static char_type
claude_context_codepoint_for(const CPUCell *cell) {
    return (cell->is_multicell || cell->ch_is_idx) ? CLAUDE_CONTEXT_OPAQUE : cell->ch_or_idx;
}

/**
 * Matches an ASCII literal against the row at x, refusing on any overrun.
 * A space in the literal matches any blank cell, not only a written space. Claude Code's
 * renderer redraws a row by moving the cursor over the runs that did not change rather than
 * re-emitting them, so the gaps between words arrive as cells that were never written and
 * hold 0. Those look identical on screen and differ only in the buffer, which is why an
 * exact byte comparison matched the same row on some redraws and not others.
 */
static bool
claude_context_literal_at(const char_type *row, index_type columns, index_type x, const char *literal, index_type literal_len) {
    if (x + literal_len > columns) return false;
    for (index_type i = 0; i < literal_len; i++) {
        if (literal[i] == ' ') {
            if (!claude_context_is_blank(row[x + i])) return false;
        } else if (row[x + i] != (char_type)literal[i]) return false;
    }
    return true;
}

/**
 * Renders a token count the way Claude Code does: a whole number below 1000, otherwise
 * thousands to one decimal with a bare ".0" dropped, which is what makes 17000 print as
 * "17k" rather than "17.0k".
 */
static index_type
claude_context_format_tokens(uint32_t tokens, char *buf, size_t capacity) {
    int len;
    if (tokens < 1000) {
        len = snprintf(buf, capacity, "%u", (unsigned int)tokens);
    } else {
        const uint32_t tenths = (tokens + 50u) / 100u;
        if (tenths % 10u == 0u) len = snprintf(buf, capacity, "%uk", (unsigned int)(tenths / 10u));
        else len = snprintf(buf, capacity, "%u.%uk", (unsigned int)(tenths / 10u), (unsigned int)(tenths % 10u));
    }
    if (len < 1 || (size_t)len >= capacity) return 0;
    return (index_type)len;
}

/**
 * Reads one of Claude Code's rendered counts ("17k", "16.7k", "337") back into tokens.
 * Deliberately strict: anything it does not recognise refuses rather than guessing, since
 * the value it returns is about to be subtracted from and redisplayed.
 */
static bool
claude_context_parse_tokens(const char_type *row, index_type x, index_type end, uint32_t *out) {
    if (x >= end) return false;
    uint32_t whole = 0;
    index_type digits = 0;
    while (x < end && row[x] >= '0' && row[x] <= '9') {
        if (whole > 100000000u) return false;
        whole = whole * 10u + (uint32_t)(row[x] - '0');
        x++; digits++;
    }
    if (!digits) return false;
    uint32_t fraction = 0;
    if (x < end && row[x] == '.') {
        x++;
        if (x >= end || row[x] < '0' || row[x] > '9') return false;
        fraction = (uint32_t)(row[x] - '0');
        x++;
        // More than one decimal place is not a shape Claude Code emits, so refuse rather
        // than silently truncating a number we do not actually understand.
        if (x < end && row[x] >= '0' && row[x] <= '9') return false;
    }
    if (x < end && row[x] == 'k') {
        *out = whole * 1000u + fraction * 100u;
        x++;
    } else {
        if (fraction) return false;
        *out = whole;
    }
    return x == end;
}

/**
 * Parses a percentage such as "4.2" into tenths, so the arithmetic stays in integers.
 */
static bool
claude_context_parse_tenths(const char_type *row, index_type x, index_type end, uint32_t *out) {
    if (x >= end) return false;
    uint32_t whole = 0;
    index_type digits = 0;
    while (x < end && row[x] >= '0' && row[x] <= '9') {
        if (whole > 100000u) return false;
        whole = whole * 10u + (uint32_t)(row[x] - '0');
        x++; digits++;
    }
    if (!digits) return false;
    uint32_t fraction = 0;
    if (x < end && row[x] == '.') {
        x++;
        if (x >= end || row[x] < '0' || row[x] > '9') return false;
        fraction = (uint32_t)(row[x] - '0');
        x++;
    }
    if (x != end) return false;
    *out = whole * 10u + fraction;
    return true;
}

/**
 * Locates the decorative block header. Pure over a row of codepoints so it can be reasoned
 * about and tested without a screen. Returns the column the literal starts at.
 */
static bool
claude_context_match_header(const char_type *row, index_type columns, index_type *header_x) {
    index_type first_non_blank = 0;
    while (first_non_blank < columns && claude_context_is_blank(row[first_non_blank])) first_non_blank++;
    if (first_non_blank >= columns || row[first_non_blank] <= 0x7f) return false;
    const index_type header_len = (index_type)(sizeof(claude_context_header) - 1);
    for (index_type x = first_non_blank; x + header_len <= columns; x++) {
        if (row[x] == CLAUDE_CONTEXT_OPAQUE) return false;
        if (!claude_context_literal_at(row, columns, x, claude_context_header, header_len)) continue;
        // The literal must be the row's last ink, so overwriting its full width cannot
        // destroy anything that follows it.
        for (index_type tail = x + header_len; tail < columns; tail++) {
            if (!claude_context_is_blank(row[tail])) return false;
        }
        *header_x = x;
        return true;
    }
    return false;
}

/**
 * Parses the "System prompt:" row into the pieces the rewrite needs. Every condition is a
 * refusal, because the alternative to refusing is rewriting a number on a row we have
 * misread.
 */
static ClaudeContextPromptRow
claude_context_match_prompt_row(const char_type *row, index_type columns, uint32_t orch_tokens) {
    ClaudeContextPromptRow ans = {0};
    index_type first_non_blank = 0;
    while (first_non_blank < columns && claude_context_is_blank(row[first_non_blank])) first_non_blank++;
    if (first_non_blank >= columns || row[first_non_blank] <= 0x7f) return ans;
    index_type bullet_x = first_non_blank;
    while (bullet_x < columns && row[bullet_x] != CLAUDE_CONTEXT_BULLET) bullet_x++;
    if (bullet_x >= columns) return ans;
    const index_type label_len = (index_type)(sizeof(claude_context_label) - 1);
    if (!claude_context_literal_at(row, columns, bullet_x + 1, claude_context_label, label_len)) return ans;
    for (index_type x = bullet_x + 1; x < columns; x++) {
        if (row[x] == CLAUDE_CONTEXT_OPAQUE) return ans;
    }
    index_type last_non_blank = columns;
    for (index_type x = columns; x-- > 0; ) {
        if (!claude_context_is_blank(row[x])) { last_non_blank = x; break; }
    }
    if (last_non_blank >= columns || row[last_non_blank] != ')') return ans;
    // "<value> tokens (<pct>%)" laid out from the label, anchored at both ends so a format
    // change shifts nothing silently.
    // Skip the whole run of blanks after the label rather than a fixed single space, for the
    // same reason the literal matcher tolerates them: a redraw can leave them unwritten.
    index_type value_x = bullet_x + 1 + label_len;
    while (value_x < last_non_blank && claude_context_is_blank(row[value_x])) value_x++;
    if (value_x >= last_non_blank) return ans;
    index_type units_x = value_x;
    const index_type units_len = (index_type)(sizeof(claude_context_units) - 1);
    while (units_x < last_non_blank && !claude_context_literal_at(row, columns, units_x, claude_context_units, units_len)) units_x++;
    if (units_x >= last_non_blank) return ans;
    if (row[last_non_blank - 1] != '%') return ans;
    const index_type percent_x = units_x + units_len;
    if (percent_x >= last_non_blank - 1) return ans;
    if (!claude_context_parse_tokens(row, value_x, units_x, &ans.tokens)) return ans;
    if (!claude_context_parse_tenths(row, percent_x, last_non_blank - 1, &ans.percent_tenths)) return ans;
    // The whole guard against rewriting twice. A row we have already reduced holds the
    // remainder, which is smaller than the layer, so a second pass refuses it. This also
    // rules out a negative result. It relies on the orchestrator layer being at least as
    // large as Claude Code's own base prompt, which it is by several times over.
    if (!ans.tokens || ans.tokens <= orch_tokens || !ans.percent_tenths) return ans;
    ans.value_x = value_x;
    ans.last_non_blank = last_non_blank;
    ans.matched = true;
    return ans;
}

/**
 * Writes ASCII over a run of cells and blanks the remainder of the old text, so a
 * replacement shorter than what it replaces cannot leave a tail behind.
 */
static void
claude_context_write(Screen *self, CPUCell *cpu_cells, GPUCell *gpu_cells, index_type x, const char *text, index_type len, index_type clear_through) {
    for (index_type i = 0; i < len; i++) {
        const index_type at = x + i;
        if (at >= self->columns) return;  // unreachable given the callers' bounds checks
        zero_at_ptr(cpu_cells + at); zero_at_ptr(gpu_cells + at);
        cell_set_char(cpu_cells + at, (char_type)text[i]);
        gpu_cells[at].attrs.dim = true;
    }
    // Zeroed rather than filled with spaces: a zeroed cell reads as genuinely empty, so the
    // row does not grow a trailing run of blanks where the old text used to be.
    for (index_type at = x + len; at <= clear_through && at < self->columns; at++) {
        zero_at_ptr(cpu_cells + at); zero_at_ptr(gpu_cells + at);
    }
}

static bool
claude_context_rewrite_header(Screen *self, CPUCell *cpu_cells, GPUCell *gpu_cells, const char_type *row, uint32_t orch_tokens) {
    index_type header_x = 0;
    if (!claude_context_match_header(row, self->columns, &header_x)) return false;
    const index_type prefix_len = (index_type)(sizeof(claude_context_header_prefix) - 1);
    char text[CLAUDE_CONTEXT_MAX_TEXT];
    memcpy(text, claude_context_header_prefix, prefix_len);
    const index_type value_len = claude_context_format_tokens(orch_tokens, text + prefix_len, sizeof(text) - prefix_len);
    if (!value_len) return false;
    const index_type len = prefix_len + value_len;
    const index_type header_len = (index_type)(sizeof(claude_context_header) - 1);
    if (header_x + len > self->columns) return false;
    // Clearing the full width of the old header is what stops a shorter replacement leaving
    // its tail behind as "Orchestrator layer: 15.4kategory".
    claude_context_write(self, cpu_cells, gpu_cells, header_x, text, len, header_x + header_len - 1);
    return true;
}

static bool
claude_context_rewrite_prompt_row(Screen *self, CPUCell *cpu_cells, GPUCell *gpu_cells, const char_type *row, uint32_t orch_tokens) {
    const ClaudeContextPromptRow parsed = claude_context_match_prompt_row(row, self->columns, orch_tokens);
    if (!parsed.matched) return false;
    const uint32_t remainder = parsed.tokens - orch_tokens;
    // Scale the percentage the row already states rather than deriving it from a context
    // window size: the ratio is exact, and the window is not on this row.
    const uint32_t percent_tenths = (uint32_t)(((uint64_t)parsed.percent_tenths * remainder + parsed.tokens / 2) / parsed.tokens);
    char value[CLAUDE_CONTEXT_MAX_TEXT];
    const index_type value_len = claude_context_format_tokens(remainder, value, sizeof(value));
    if (!value_len) return false;
    char text[CLAUDE_CONTEXT_MAX_TEXT];
    const int len = snprintf(text, sizeof(text), "%s%s%u.%u%%)", value, claude_context_units,
                             (unsigned int)(percent_tenths / 10u), (unsigned int)(percent_tenths % 10u));
    if (len < 1 || (size_t)len >= sizeof(text)) return false;
    if (parsed.value_x + (index_type)len > self->columns) return false;
    claude_context_write(self, cpu_cells, gpu_cells, parsed.value_x, text, (index_type)len, parsed.last_non_blank);
    return true;
}

static void
claude_context_annotate_row(Screen *self, index_type y, uint32_t orch_tokens) {
    if (self->columns > CLAUDE_CONTEXT_MAX_COLUMNS) return;
    CPUCell *cpu_cells; GPUCell *gpu_cells;
    linebuf_init_cells(self->linebuf, y, &cpu_cells, &gpu_cells);
    // Cheap prefilter, repeated inside each predicate so those stay complete on their own.
    // It rejects essentially all ordinary output on one comparison, before the row is copied.
    char_type first_ink = 0;
    for (index_type x = 0; x < self->columns && !first_ink; x++) {
        const char_type codepoint = claude_context_codepoint_for(cpu_cells + x);
        if (!claude_context_is_blank(codepoint)) first_ink = codepoint;
    }
    if (first_ink <= 0x7f) return;
    char_type row[CLAUDE_CONTEXT_MAX_COLUMNS];
    for (index_type x = 0; x < self->columns; x++) row[x] = claude_context_codepoint_for(cpu_cells + x);
    // A row is one or the other, never both, so the header attempt short-circuits.
    const bool written = claude_context_rewrite_header(self, cpu_cells, gpu_cells, row, orch_tokens)
        || claude_context_rewrite_prompt_row(self, cpu_cells, gpu_cells, row, orch_tokens);
    if (!written) return;
    linebuf_mark_line_dirty(self->linebuf, y);
    self->is_dirty = true;
}

static uint32_t
claude_context_session_tokens(Screen *self) {
    if (!OPT(claude_context_breakdown)) return 0;
    return self->claude_orch_tokens;
}

void
screen_annotate_claude_context_row(Screen *self, index_type y) {
    const uint32_t orch_tokens = claude_context_session_tokens(self);
    if (!orch_tokens) return;
    claude_context_annotate_row(self, y, orch_tokens);
}

void
screen_annotate_claude_context_dirty_rows(Screen *self) {
    const uint32_t orch_tokens = claude_context_session_tokens(self);
    if (!orch_tokens) return;
    for (index_type y = 0; y < self->lines; y++) {
        if (self->linebuf->line_attrs[y].has_dirty_text) claude_context_annotate_row(self, y, orch_tokens);
    }
}
// }}}
