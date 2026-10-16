"""A small, bounded Python drawing interface for generated scenes."""
import ast
import contextlib
import math
import signal
from pathlib import Path

from PIL import Image, ImageDraw

METHODS = {'line', 'ellipse', 'rectangle', 'polygon', 'arc', 'point'}
MATH = {'sin', 'cos', 'tan', 'sqrt', 'hypot', 'atan2', 'floor', 'ceil', 'pi', 'tau', 'fabs'}
CALLS = {'range', 'min', 'max', 'abs', 'int', 'float', 'len'}
NODES = {ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.Assign,
         ast.AugAssign, ast.Expr, ast.Return, ast.For, ast.If, ast.IfExp,
         ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.Call, ast.keyword,
         ast.Name, ast.Load, ast.Store, ast.Constant, ast.Num, ast.Str,
         ast.NameConstant, ast.List, ast.Tuple, ast.Subscript, ast.Index,
         ast.Slice, ast.Attribute, ast.ListComp, ast.comprehension,
         ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod,
         ast.UAdd, ast.USub, ast.Not, ast.And, ast.Or, ast.Eq, ast.NotEq,
         ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Pass, ast.Break, ast.Continue}


def bounded_range(*args):
    result = range(*args)
    if len(result) > 128:
        raise ValueError('range may contain at most 128 values')
    return result


def check_source(source):
    if len(source.encode()) > 20000:
        raise ValueError('Scene is too large')
    tree = ast.parse(source)
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
        raise ValueError('Supply only def draw_frame(draw, t, audio, width, height)')
    fn = tree.body[0]
    if fn.name != 'draw_frame' or fn.decorator_list or fn.returns:
        raise ValueError('Invalid drawing function')
    args = fn.args
    if ([a.arg for a in args.args] != ['draw', 't', 'audio', 'width', 'height']
            or args.defaults or args.kwonlyargs or args.vararg or args.kwarg
            or getattr(args, 'posonlyargs', [])):
        raise ValueError('Unexpected function signature')
    nodes = list(ast.walk(tree))
    if len(nodes) > 1600:
        raise ValueError('Scene is too complex')
    for node in nodes:
        if type(node) not in NODES:
            raise ValueError('Unsupported syntax: '+type(node).__name__)
        if isinstance(node, ast.FunctionDef) and node is not fn:
            raise ValueError('Nested functions are not supported')
        if isinstance(node, ast.arg) and node.annotation:
            raise ValueError('Annotations are not supported')
        if isinstance(node, ast.Name) and node.id.startswith('_'):
            raise ValueError('Private names are not allowed')
        if isinstance(node, ast.Attribute):
            if not isinstance(node.ctx, ast.Load) or not isinstance(node.value, ast.Name):
                raise ValueError('Only drawing and math attributes are allowed')
            allowed = METHODS if node.value.id == 'draw' else MATH if node.value.id == 'math' else set()
            if node.attr not in allowed:
                raise ValueError('Unsupported attribute: '+node.attr)
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id not in CALLS:
                    raise ValueError('Unsupported function: '+node.func.id)
            elif not isinstance(node.func, ast.Attribute):
                raise ValueError('Indirect calls are not allowed')
            if any(k.arg is None for k in node.keywords):
                raise ValueError('Expanded arguments are not allowed')
    return tree


def compile_scene(source):
    tree = check_source(source)
    safe = {'range': bounded_range, 'min': min, 'max': max, 'abs': abs,
            'int': int, 'float': float, 'len': len}
    scope = {'__builtins__': {}, 'math': math, **safe}
    exec(compile(tree, '<daily-scene>', 'exec'), scope)
    return scope['draw_frame']


@contextlib.contextmanager
def deadline(seconds):
    def expired(*_):
        raise TimeoutError('Drawing exceeded its frame budget')
    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


class Canvas:
    def __init__(self, image):
        self.pen = ImageDraw.Draw(image)
        self.calls = 0

    def paint(self, method, xy, **kwargs):
        self.calls += 1
        if self.calls > 256:
            raise ValueError('Too many drawing operations')
        if len(xy) > 256:
            raise ValueError('Too many points')
        values = []
        for item in xy:
            values.extend(item if isinstance(item, (tuple, list)) else [item])
        if any(not isinstance(x, (int, float)) or not math.isfinite(x) or abs(x) > 2048 for x in values):
            raise ValueError('Coordinates outside drawing bounds')
        if not 1 <= kwargs.get('width', 1) <= 12:
            raise ValueError('Line width must be 1..12')
        return getattr(self.pen, method)(xy, **kwargs)

    def line(self, xy, *args, **kwargs):
        # Tiny coding models often pass the two endpoints separately.
        if (len(xy) == 2 and all(isinstance(x, (int, float)) for x in xy)
                and args and isinstance(args[0], (tuple, list)) and len(args[0]) == 2):
            xy, args = (xy, args[0]), args[1:]
            if not args:
                kwargs.setdefault('fill', (180, 220, 240))
        if len(args) > 2:
            raise TypeError('Too many line arguments')
        for name, value in zip(('fill', 'width'), args):
            if name in kwargs:
                raise TypeError('Repeated line argument: '+name)
            kwargs[name] = value
        return self.paint('line', xy, **kwargs)

    def ellipse(self, xy, fill=None, outline=None, width=1):
        # A single point denotes a small dot; four values still denote a box.
        if len(xy) == 2 and all(isinstance(x, (int, float)) for x in xy):
            x, y = xy
            xy = (x-3, y-3, x+3, y+3)
        return self.paint('ellipse', xy, fill=fill, outline=outline, width=width)

    def rectangle(self, xy, fill=None, outline=None, width=1):
        return self.paint('rectangle', xy, fill=fill, outline=outline, width=width)

    def polygon(self, xy, fill=None, outline=None):
        return self.paint('polygon', xy, fill=fill, outline=outline)

    def arc(self, xy, start, end, fill=None, width=1):
        return self.paint('arc', xy, start=start, end=end, fill=fill, width=width)

    def point(self, xy, fill=None):
        return self.paint('point', xy, fill=fill)


def draw_scene(function, t, audio, budget=.04):
    image = Image.new('RGB', (360, 360), '#080e19')
    with deadline(budget):
        function(Canvas(image), t, audio, 360, 360)
    return image


class DailyScene:
    def __init__(self, path):
        self.path = Path(path)
        self.signature = None
        self.function = None
        self.next_check = 0

    def render(self, state, now, bpm):
        if now >= self.next_check:
            self.next_check = now+30
            try:
                stat = self.path.stat()
                signature = (stat.st_mtime_ns, stat.st_size)
                if signature != self.signature:
                    self.signature = signature
                    self.function = compile_scene(self.path.read_text())
                    print('Loaded daily scene', flush=True)
            except FileNotFoundError:
                pass
            except Exception as exc:
                self.function = None
                print('Scene rejected: '+str(exc), flush=True)
        if self.function is None:
            return None
        quiet = now-state.last_sound > 3
        audio = {'level': float(state.display_level),
                 'bands': tuple(float(x) for x in state.display_bars),
                 'quiet': quiet, 'pulse': math.exp(-((now*bpm/60) % 1)*5)}
        try:
            return draw_scene(self.function, now, audio)
        except Exception as exc:
            self.function = None
            print('Daily scene failed; using built-in display: '+str(exc), flush=True)
            return None
