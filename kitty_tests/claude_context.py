#!/usr/bin/env python
# License: GPL v3 Copyright: 2016, Kovid Goyal <kovid at kovidgoyal.net>

"""
Tests for the Claude Code context breakdown filter. Kept in their own module for the same
reason the implementation is: see kitty/claude-context.h.
"""

from . import BaseTest

# The System prompt row of Claude Code's /context report, captured live. The grid squares
# are U+26F6, the bullet is U+26C1, the label is at column 49 rather than at line start and
# the row ends in a closing paren. Content occupies 83 of the 142 columns it was captured at.
CLAUDE_CONTEXT_ROW = '⛶ ' * 22 + '   ⛁ System prompt: 25.1k tokens (2.5%)'
CLAUDE_CONTEXT_HEADER_ROW = '⛶ ' * 22 + '   Estimated usage by category'
# 22k of the row's 25.1k, leaving 3.1k and a percentage scaled by that same ratio.
CLAUDE_ORCH_TOKENS = 22000
CLAUDE_CONTEXT_REWRITTEN_ROW = '⛶ ' * 22 + '   ⛁ System prompt: 3.1k tokens (0.3%)'
# Laid out like the report's own data rows: bullet, label in the terminal default,
# then the value in the grey the report uses for values.
CLAUDE_CONTEXT_REWRITTEN_HEADER = '⛶ ' * 22 + '   ⛁ Orchestrator layer: 22k'
# Rows from the same report that share its shape and must never be annotated.
CLAUDE_CONTEXT_SIBLING_ROWS = (
    '⛁ Messages: 7 tokens (0.0%)',
    '⛶ Free space: 934.9k (93.5%)',
    '⛁ System tools: 8.1k tokens (0.8%)',
    '⛁ Memory files: 28.1k tokens (2.8%)',
    '⛁ Custom agents: 429 tokens (0.0%)',
)


class TestClaudeContext(BaseTest):

    def claude_context_screen(self, row=CLAUDE_CONTEXT_ROW, cols=142, tokens=CLAUDE_ORCH_TOKENS, enabled=True):
        s = self.create_screen(cols=cols, lines=5, options={'claude_context_breakdown': enabled})
        s.claude_orch_tokens = tokens
        s.draw(row)
        return s

    def test_claude_context_breakdown_captured_rows(self):
        # The ground truth both predicates are anchored to, asserted here so a change to the
        # fixtures cannot quietly stop exercising the shape that was measured.
        self.ae(CLAUDE_CONTEXT_ROW.index('System prompt:'), 49)
        self.ae(CLAUDE_CONTEXT_ROW[47:49], '⛁ ')
        self.ae(CLAUDE_CONTEXT_ROW[-1], ')')
        self.ae(CLAUDE_CONTEXT_HEADER_ROW.index('Estimated usage by category'), 47)
        self.ae(CLAUDE_CONTEXT_HEADER_ROW[-1], 'y')

    def test_claude_context_breakdown_rewrites_prompt_row(self):
        s = self.claude_context_screen()
        s.annotate_claude_context_dirty_rows()
        self.ae(str(s.line(0)), CLAUDE_CONTEXT_REWRITTEN_ROW)

    def test_claude_context_breakdown_overwrites_header(self):
        s = self.claude_context_screen(row=CLAUDE_CONTEXT_HEADER_ROW)
        s.annotate_claude_context_dirty_rows()
        self.ae(str(s.line(0)), CLAUDE_CONTEXT_REWRITTEN_HEADER)

    def test_claude_context_breakdown_clears_the_full_old_header(self):
        # The replacement is shorter than the literal it replaces, so a clear that stops at
        # the replacement's own width leaves the literal's tail behind as
        # "Orchestrator layer: 22kgory". Assert on the exact row: a substring check for the
        # whole word misses the shorter residue that actually survives.
        s = self.claude_context_screen(row=CLAUDE_CONTEXT_HEADER_ROW)
        s.annotate_claude_context_dirty_rows()
        line = str(s.line(0))
        self.ae(line, CLAUDE_CONTEXT_REWRITTEN_HEADER)
        for residue in ('gory', 'ategory', 'Estimated'):
            self.assertNotIn(residue, line)

    def test_claude_context_breakdown_scales_the_percentage(self):
        # 3.1k of the row's original 25.1k is 12.4% of it, so 2.5% becomes 0.3%.
        s = self.claude_context_screen()
        s.annotate_claude_context_dirty_rows()
        self.assertIn('3.1k tokens (0.3%)', str(s.line(0)))

    def test_claude_context_breakdown_formats_like_claude_code(self):
        # A whole number below 1000, thousands to one decimal, and a bare .0 dropped.
        for tokens, expected in ((25000, '100 tokens'), (24000, '1.1k tokens'), (22100, '3k tokens')):
            s = self.claude_context_screen(tokens=tokens)
            s.annotate_claude_context_dirty_rows()
            self.assertIn(expected, str(s.line(0)))

    def claude_context_gapped_screen(self, tokens=CLAUDE_ORCH_TOKENS):
        # Reproduces how Claude Code's renderer actually redraws a row it has already shown:
        # the runs that did not change are skipped with cursor motion rather than re-emitted,
        # so the gaps between words are cells that were never written and hold 0 rather than
        # a space. Visually identical, and it made the match succeed or fail depending only
        # on what the previous frame looked like.
        s = self.create_screen(cols=142, lines=5, options={'claude_context_breakdown': True})
        s.claude_orch_tokens = tokens
        s.draw('⛶ ' * 22)
        for x, text in ((47, '⛁'), (49, 'System'), (56, 'prompt:'), (64, '25.1k tokens (2.5%)')):
            s.cursor.x = x
            s.draw(text)
        return s

    def test_claude_context_breakdown_row_redrawn_with_cursor_motion(self):
        s = self.claude_context_gapped_screen()
        # The gaps really are unwritten, not spaces: that is the whole point of the fixture.
        line = str(s.line(0))
        self.ae(line[48], ' ')
        self.assertIn('⛁', line)
        self.assertIn('System', line)
        s.annotate_claude_context_dirty_rows()
        self.assertIn('3.1k tokens (0.3%)', str(s.line(0)))

    def test_claude_context_breakdown_refuses_when_option_off(self):
        for row in (CLAUDE_CONTEXT_ROW, CLAUDE_CONTEXT_HEADER_ROW):
            s = self.claude_context_screen(row=row, enabled=False)
            s.annotate_claude_context_dirty_rows()
            self.ae(str(s.line(0)), row)

    def test_claude_context_breakdown_refuses_unmarked_window(self):
        for row in (CLAUDE_CONTEXT_ROW, CLAUDE_CONTEXT_HEADER_ROW):
            s = self.claude_context_screen(row=row, tokens=0)
            s.annotate_claude_context_dirty_rows()
            self.ae(str(s.line(0)), row)

    def test_claude_context_breakdown_refuses_ascii_row_start(self):
        for source in (CLAUDE_CONTEXT_ROW, CLAUDE_CONTEXT_HEADER_ROW):
            row = '- ' + source.lstrip('⛶ ')
            self.ae(row[0], '-')
            s = self.claude_context_screen(row=row)
            s.annotate_claude_context_dirty_rows()
            self.ae(str(s.line(0)), row)

    def test_claude_context_breakdown_refuses_wrong_label(self):
        for row in (CLAUDE_CONTEXT_ROW.replace('System prompt:', 'System Prompt:'),
                    CLAUDE_CONTEXT_HEADER_ROW.replace('Estimated usage', 'Estimated Usage')):
            s = self.claude_context_screen(row=row)
            s.annotate_claude_context_dirty_rows()
            self.ae(str(s.line(0)), row)

    def test_claude_context_breakdown_refuses_sibling_rows(self):
        prefix = CLAUDE_CONTEXT_ROW[:47]
        for sibling in CLAUDE_CONTEXT_SIBLING_ROWS:
            row = prefix + sibling
            s = self.claude_context_screen(row=row)
            s.annotate_claude_context_dirty_rows()
            self.ae(str(s.line(0)), row)

    def test_claude_context_breakdown_refuses_row_not_ending_in_paren(self):
        row = CLAUDE_CONTEXT_ROW + ' ...'
        s = self.claude_context_screen(row=row)
        s.annotate_claude_context_dirty_rows()
        self.ae(str(s.line(0)), row)

    def test_claude_context_breakdown_refuses_header_with_trailing_text(self):
        # The literal is no longer the row's last ink, so overwriting its width would
        # destroy whatever follows.
        row = CLAUDE_CONTEXT_HEADER_ROW + ' (detail)'
        s = self.claude_context_screen(row=row)
        s.annotate_claude_context_dirty_rows()
        self.ae(str(s.line(0)), row)

    def test_claude_context_breakdown_refuses_unparseable_value(self):
        for bad in ('25.1.2k', 'about 25k', '25.1kk'):
            row = CLAUDE_CONTEXT_ROW.replace('25.1k', bad)
            s = self.claude_context_screen(row=row)
            s.annotate_claude_context_dirty_rows()
            self.ae(str(s.line(0)), row)

    def test_claude_context_breakdown_refuses_unparseable_percentage(self):
        # 'two' has no digits at all; '2.5x' parses as a number and then has trailing
        # characters, which is the case that exercises the parser's end anchor rather
        # than its digit check.
        for bad in ('(two%)', '(2.5x%)', '(2.5.1%)'):
            row = CLAUDE_CONTEXT_ROW.replace('(2.5%)', bad)
            s = self.claude_context_screen(row=row)
            s.annotate_claude_context_dirty_rows()
            self.ae(str(s.line(0)), row)

    def test_claude_context_breakdown_refuses_when_layer_exceeds_total(self):
        # Subtracting would go negative. This is also what makes a second pass a no-op.
        s = self.claude_context_screen(tokens=25100)
        s.annotate_claude_context_dirty_rows()
        self.ae(str(s.line(0)), CLAUDE_CONTEXT_ROW)
        s = self.claude_context_screen(tokens=30000)
        s.annotate_claude_context_dirty_rows()
        self.ae(str(s.line(0)), CLAUDE_CONTEXT_ROW)

    def test_claude_context_breakdown_refuses_wide_character_in_row(self):
        # A width two character makes its cells multicell, and the filter refuses any row
        # holding one. Note this row is decided by the parse failing first (the wide char
        # lands on the " tokens (" anchor), so the multicell check behind it is
        # defence in depth rather than the deciding refusal for this shape.
        s = self.claude_context_screen()
        s.cursor.x, s.cursor.y = 70, 0
        s.draw('ネ')
        expected = CLAUDE_CONTEXT_ROW[:70] + 'ネ' + CLAUDE_CONTEXT_ROW[72:]
        self.ae(str(s.line(0)), expected)
        s.annotate_claude_context_dirty_rows()
        self.ae(str(s.line(0)), expected)

    def test_claude_context_breakdown_refuses_beyond_scan_buffer_width(self):
        s = self.claude_context_screen(cols=1025)
        s.annotate_claude_context_dirty_rows()
        self.ae(str(s.line(0)), CLAUDE_CONTEXT_ROW)

    def test_claude_context_breakdown_does_not_rewrite_twice(self):
        # A second subtraction would visibly count the number down every frame. The row now
        # holds the remainder, which is smaller than the layer, so the guard refuses it.
        for row, expected in ((CLAUDE_CONTEXT_ROW, CLAUDE_CONTEXT_REWRITTEN_ROW),
                              (CLAUDE_CONTEXT_HEADER_ROW, CLAUDE_CONTEXT_REWRITTEN_HEADER)):
            s = self.claude_context_screen(row=row)
            s.annotate_claude_context_dirty_rows()
            self.ae(str(s.line(0)), expected)
            # Strip the filter's own styling and leave every row dirty, so the next scan
            # reaches the row and any write it makes is visible.
            s.linebuf.set_attribute('dim', 0)
            self.assertIn(0, s.linebuf.dirty_lines())
            undimmed = s.line(0).as_ansi()
            s.annotate_claude_context_dirty_rows()
            self.ae(str(s.line(0)), expected)
            self.ae(s.line(0).as_ansi(), undimmed)

    def test_claude_context_breakdown_header_carries_the_row_bullet(self):
        s = self.claude_context_screen(row=CLAUDE_CONTEXT_HEADER_ROW)
        s.annotate_claude_context_dirty_rows()
        self.assertIn('⛁ Orchestrator layer:', str(s.line(0)))

    def test_claude_context_breakdown_does_not_force_a_dim_style(self):
        # It used to write everything dim, which rendered grey where the report's own label
        # is the terminal default. Clearing dim afterwards must therefore change nothing.
        s = self.claude_context_screen()
        s.annotate_claude_context_dirty_rows()
        styled = s.line(0).as_ansi()
        self.assertIn('3.1k', styled)
        s.linebuf.set_attribute('dim', 0)
        self.ae(s.line(0).as_ansi(), styled)

    def test_claude_context_breakdown_inherits_the_replaced_styling(self):
        # The value it writes takes the styling of the text it replaced. Only the value is
        # drawn dim here: dimming the whole row instead would make the assertion pass on the
        # untouched cells no matter what the filter wrote.
        s = self.create_screen(cols=142, lines=5, options={'claude_context_breakdown': True})
        s.claude_orch_tokens = CLAUDE_ORCH_TOKENS
        # The separating space is drawn BEFORE dim is enabled: it sits outside the region the
        # filter overwrites, so leaving it dim would keep the assertion alive on a cell the
        # filter never touched.
        s.draw('⛶ ' * 22 + '   ⛁ System prompt: ')
        s.select_graphic_rendition(2)  # dim, covering exactly the cells the filter replaces
        s.draw('25.1k tokens (2.5%)')
        s.select_graphic_rendition(0)
        self.ae(str(s.line(0)), CLAUDE_CONTEXT_ROW)
        s.annotate_claude_context_dirty_rows()
        self.assertIn('3.1k', str(s.line(0)))
        styled = s.line(0).as_ansi()
        s.linebuf.set_attribute('dim', 0)
        self.assertNotEqual(s.line(0).as_ansi(), styled, 'the rewritten value did not keep the dim it replaced')

    def test_claude_context_breakdown_ignores_the_cursor_style(self):
        # Whatever SGR the cursor happens to carry when the filter runs must not leak in.
        s = self.claude_context_screen()
        s.select_graphic_rendition(1)  # bold
        s.annotate_claude_context_dirty_rows()
        styled = s.line(0).as_ansi()
        s.linebuf.set_attribute('bold', 0)
        self.ae(s.line(0).as_ansi(), styled)

    def test_claude_context_breakdown_leaves_the_grid_alone(self):
        s = self.claude_context_screen()
        cursor_before = (s.cursor.x, s.cursor.y)
        history_before = s.historybuf.count
        s.annotate_claude_context_dirty_rows()
        self.ae((s.cursor.x, s.cursor.y), cursor_before)
        self.ae(s.historybuf.count, history_before)
        self.assertLessEqual(len(str(s.line(0))), s.columns)
        for y in range(1, s.lines):
            self.ae(str(s.line(y)), '')

    def test_claude_context_breakdown_annotates_on_history_eviction(self):
        # The row scrolls off before any render pass, so only the eviction trigger can reach it.
        s = self.claude_context_screen()
        for _ in range(s.lines):
            s.linefeed()
        self.ae(str(s.historybuf.line(0)), CLAUDE_CONTEXT_REWRITTEN_ROW)
        s = self.claude_context_screen(enabled=False)
        for _ in range(s.lines):
            s.linefeed()
        self.ae(str(s.historybuf.line(0)), CLAUDE_CONTEXT_ROW)
