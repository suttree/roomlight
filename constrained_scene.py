"""Grammar-constrained Python scenes with tested structure and bounded variation."""
import colorsys
import json
import re

THEMES = ['orbiting moons', 'sound ripples', 'a geometric flower',
          'a constellation', 'waves', 'a spiral of dots', 'rotating spokes',
          'falling rain', 'woven lines', 'a slowly breathing sun',
          'dancing columns', 'radial sparks', 'classic spectrum bars',
          'a mirrored equaliser', 'a radial spectrum', 'an oscilloscope-style wave']

BODIES = [
'''angle = i*math.pi/4+t*.3
radius = 55+i*4+20*energy
x = 180+radius*math.cos(angle)
y = 180+radius*math.sin(angle)
r = 6+25*energy
draw.ellipse((x-r,y-r,x+r,y+r), fill=@COLOUR@)''',
'''r = 10+(i*13+t*35)%110+30*energy
draw.ellipse((180-r,180-r,180+r,180+r), outline=@COLOUR@, width=3)''',
'''angle = i*math.pi/4+t*.15
r = 60+60*energy+25*math.sin(t+i)
draw.line((180,180,180+r*math.cos(angle),180+r*math.sin(angle)), fill=@COLOUR@, width=6)''',
'''x = 45+(i*43)%270
y = 180+100*math.sin(t*.5+i*.7)
r = 6+25*energy
draw.ellipse((x-r,y-r,x+r,y+r), fill=@COLOUR@)''',
'''x = 20+i*40
y = 160+60*math.sin(t+i*.5)
draw.line((x,y,x+8,y+100*energy), fill=@COLOUR@, width=6)''',
'''angle = i*.65+t*.3
radius = 20+i*12
x = 180+radius*math.cos(angle)
y = 180+radius*math.sin(angle)
r = 6+25*energy
draw.ellipse((x-r,y-r,x+r,y+r), fill=@COLOUR@)''',
'''angle = i*math.pi/4-t*.4
r = 55+100*energy
draw.line((180+40*math.cos(angle),180+40*math.sin(angle),180+r*math.cos(angle),180+r*math.sin(angle)), fill=@COLOUR@, width=6)''',
'''x = 20+i*40
y = (t*35+i*31)%220
draw.line((x,y,x,y+8+115*energy), fill=@COLOUR@, width=6)''',
'''y = 20+i*40
end = 180+120*math.sin(t*.4+i*.25)*(.3+energy*.7)
draw.line((20,y,340,end), fill=@COLOUR@, width=4)''',
'''r = 10+i*12+30*energy+5*math.sin(t)
draw.ellipse((180-r,180-r,180+r,180+r), outline=@COLOUR@, width=3)''',
'''x = 25+i*40
h = 10+180*energy*(.5+.5*math.sin(t+i))
draw.line((x,320,x,320-h), fill=@COLOUR@, width=10)''',
'''angle = i*math.pi/4
radius = 20+(t*35+i*9)%70
r = radius+5+70*energy
draw.line((180+radius*math.cos(angle),180+radius*math.sin(angle),180+r*math.cos(angle),180+r*math.sin(angle)), fill=@COLOUR@, width=8)''',
'''x = 25+i*40
h = 12+220*energy+4*math.sin(t*2+i)
draw.line((x,320,x,320-h), fill=@COLOUR@, width=12)''',
'''x = 25+i*40
h = 8+140*energy+3*math.sin(t*2+i)
draw.line((x,180-h,x,180+h), fill=@COLOUR@, width=10)''',
'''angle = i*math.pi/4+t*.15
r = 65+95*energy
draw.line((180+45*math.cos(angle),180+45*math.sin(angle),180+r*math.cos(angle),180+r*math.sin(angle)), fill=@COLOUR@, width=10)''',
'''amplitude = 12+135*energy
x = 20+i*40
next_x = x+40
y = 180+amplitude*math.sin(i*math.pi/2+t*2)
next_y = 180+amplitude*math.sin((i+1)*math.pi/2+t*2)
draw.line((x,y,next_x,next_y), fill=@COLOUR@, width=6)''']


def scene_spec(day):
    index = day.toordinal() % len(THEMES)
    palette = [tuple(int(c*255) for c in colorsys.hsv_to_rgb(
        (day.toordinal()*.61803398875+shift) % 1, .65, 1)) for shift in (0, .15, .35)]
    options = {'SPEED': ['0.6', '0.9', '1.2'], 'PHASE': ['0.0', '1.5', '3.0'],
               'GAIN': ['1.0', '1.2', '1.4'], 'COLOUR': [repr(c) for c in palette]}
    template = """def draw_frame(draw, t, audio, width, height):
    t = t * @SPEED@ + @PHASE@
    strength = audio['pulse'] if audio['quiet'] else audio['level']
    for i in range(8):
        energy = min(1, @GAIN@ * (strength if audio['quiet'] else .6*strength+.4*audio['bands'][i*3]))
""" + ''.join('        '+line+'\n' for line in BODIES[index].splitlines())
    return THEMES[index], template, options


def grammar_for(day):
    theme, template, options = scene_spec(day)
    parts = re.split(r'(@[A-Z]+@)', template)
    root = ' '.join(part[1:-1].lower() if part.startswith('@') else json.dumps(part)
                    for part in parts if part)
    rules = ['root ::= '+root]
    rules.extend(key.lower()+' ::= '+' | '.join(json.dumps(value) for value in values)
                 for key, values in options.items())
    return theme, '\n'.join(rules)+'\n'


def matches_spec(code, day):
    _, template, options = scene_spec(day)
    pattern = re.escape(template.strip())
    for key, values in options.items():
        pattern = pattern.replace(re.escape('@'+key+'@'), '(?:'+'|'.join(re.escape(v) for v in values)+')')
    return re.fullmatch(pattern, code.strip()) is not None
