"""A small Python grammar for composing new layouts, not selecting scene bodies."""
import ast
import datetime
import json

from scenes import check_source

PREFIX = """def draw_frame(draw, t, audio, width, height):
    strength = audio['level']
    for i in range(8):
        energy = min(1, .6*strength+.4*audio['bands'][i*3])
"""

GRAMMAR = r'''
coordinate ::= "180 + 120 * math.sin(" expression " + i)" | "180 + 120 * math.cos(" expression " + i)" | "60 + ((" expression " + 31 * i) % 240)" | "60 + 30 * i" | "180 + (40 + 80 * energy) * math.sin(" expression " + i)" | "180 + (40 + 80 * energy) * math.cos(" expression " + i)"
expression ::= term | term " + " term | term " - " term
term ::= atom | atom " * " atom
atom ::= number | "t" | "i" | "energy" | "math.pi" | "math.sin(" simple ")" | "math.cos(" simple ")"
simple ::= variable | variable " * " number | variable " + " variable | variable " - " variable
variable ::= "t" | "i" | "energy"
number ::= "0." [1-9] | [1-9] "." [0-9]

'''


# Saturated palettes cycle across the eight shapes; no neutral/white option.
PALETTES = (
    ((255, 72, 112), (255, 164, 48), (160, 64, 255), (40, 208, 224)),
    ((40, 232, 168), (40, 152, 255), (176, 72, 255), (255, 64, 160)),
    ((255, 88, 40), (255, 192, 40), (224, 48, 136), (112, 64, 240)),
)

# Each is a single bounded drawing call, compatible with the Pi's older Pillow.
PAINTS = (
    'draw.ellipse((x-r,y-r*.5,x+r,y+r*.5), outline=colour, width=4)',
    'draw.arc((x-r,y-r,x+r,y+r), start=(angle*57.3)%360, end=(angle*57.3)%360+240, fill=colour, width=6)',
    'draw.line((x-r,y+r*math.sin(angle),x-r*.3,y-r,x+r*.3,y+r,x+r,y-r*math.sin(angle)), fill=colour, width=6)',
    'draw.polygon((x-r,y,x+r*.3,y-r,x+r,y+r*.3,x-r*.2,y+r*.6), fill=colour)',
    'draw.polygon((x-r*math.cos(angle),y-r*math.sin(angle),x+r*math.sin(angle)*.4,y-r*math.cos(angle)*.4,x+r*math.cos(angle),y+r*math.sin(angle)), fill=colour)',
    'draw.line((x-r,y-r,x,y+r,x+r,y-r*.4), fill=colour, width=8)',
)

GRAMMAR += 'colour ::= '+ ' | '.join(json.dumps(repr(palette)+'[i % 4]') for palette in PALETTES)+'\n'
GRAMMAR += 'paint ::= '+ ' | '.join(json.dumps(paint) for paint in PAINTS)+'\n'


def motion_policy(day):
    # Only Sunday permits two moving axes. Other days cannot form an orbit.
    policies = (
        ('vertical paths', '"60 + 30 * i"', 'coordinate'),
        ('horizontal paths', 'coordinate', '"60 + 30 * i"'),
        ('moving columns', '"60 + 75 * (i % 4)"', 'coordinate'),
        ('moving rows', 'coordinate', '"90 + 120 * (i // 4)"'),
        ('vertical paths', '"60 + 30 * i"', 'coordinate'),
        ('horizontal paths', 'coordinate', '"60 + 30 * i"'),
        ('open motion', 'coordinate', 'coordinate'))
    return policies[day.weekday()]


def grammar_for_method(day=None):
    _, x_rule, y_rule = motion_policy(day or datetime.date.today())
    parts = [json.dumps(PREFIX+'        x = '), 'x-coordinate',
             json.dumps('\n        y = '), 'y-coordinate',
             json.dumps('\n        r = 8 + 40 * energy\n        angle = '), 'expression',
             json.dumps('\n        colour = '), 'colour',
             json.dumps('\n        '), 'paint', json.dumps('\n')]
    return ('root ::= '+' '.join(parts)+'\n'
            +'x-coordinate ::= '+x_rule+'\n'
            +'y-coordinate ::= '+y_rule+'\n'+GRAMMAR)


def matches_method(code):
    """Independently check required structure and names before runtime validation."""
    try:
        tree = check_source(code)
        if not code.startswith(PREFIX):
            return False
        fn = tree.body[0]
        if len(fn.body) != 2 or not isinstance(fn.body[1], ast.For):
            return False
        statements = fn.body[1].body
        if len(statements) != 7:
            return False
        known = {'t', 'i', 'strength', 'audio', 'math', 'min', 'draw'}
        for statement, name in zip(statements[:-1], ('energy', 'x', 'y', 'r', 'angle', 'colour')):
            if (not isinstance(statement, ast.Assign) or len(statement.targets) != 1
                    or not isinstance(statement.targets[0], ast.Name)
                    or statement.targets[0].id != name):
                return False
            if any(isinstance(node, ast.Name) and node.id not in known
                   for node in ast.walk(statement.value)):
                return False
            known.add(name)
        last = statements[-1]
        if not isinstance(last, ast.Expr) or not isinstance(last.value, ast.Call):
            return False
        if any(isinstance(node, ast.Name) and node.id not in known for node in ast.walk(last)):
            return False
        return isinstance(last.value.func, ast.Attribute) and last.value.func.value.id == 'draw'
    except (ValueError, SyntaxError, AttributeError):
        return False


def layout_signature(code):
    """Ignore palette and numeric tuning when comparing procedural layouts."""
    tree = check_source(code)
    class Layout(ast.NodeTransformer):
        def visit_Assign(self, node):
            if any(isinstance(target, ast.Name) and target.id == 'colour' for target in node.targets):
                return None
            return self.generic_visit(node)

        def visit_Num(self, node):
            node.n = 0
            return node

        def visit_Constant(self, node):
            if isinstance(node.value, (int, float)):
                node.value = 0
            return node
    return ast.dump(Layout().visit(tree))
