"""A small Python grammar for composing new layouts, not selecting scene bodies."""
import ast
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
channel ::= "64" | "96" | "128" | "160" | "192" | "224" | "255"
colour ::= "(" channel ", " channel ", " channel ")"
paint ::= "draw.ellipse((x-r,y-r,x+r,y+r), fill=colour)" | "draw.ellipse((x-r,y-r,x+r,y+r), outline=colour, width=4)" | "draw.rectangle((x-r,y-r,x+r,y+r), fill=colour)" | "draw.rectangle((x-r,y-r,x+r,y+r), outline=colour, width=4)" | "draw.line((x-r*math.cos(angle),y-r*math.sin(angle),x+r*math.cos(angle),y+r*math.sin(angle)), fill=colour, width=8)" | "draw.polygon((x,y-r,x+r,y+r,x-r,y+r), fill=colour)"
'''


def grammar_for_method():
    parts = [json.dumps(PREFIX+'        x = '), 'coordinate',
             json.dumps('\n        y = '), 'coordinate',
             json.dumps('\n        r = 8 + 40 * energy\n        angle = '), 'expression',
             json.dumps('\n        colour = '), 'colour',
             json.dumps('\n        '), 'paint', json.dumps('\n')]
    return 'root ::= '+' '.join(parts)+'\n'+GRAMMAR


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
