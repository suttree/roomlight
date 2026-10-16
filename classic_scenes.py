"""Handwritten daily fallbacks. These are not model-generated scenes."""
import colorsys

NAMES = ('classic spectrum bars', 'a mirrored equaliser', 'a radial spectrum',
         'an oscilloscope-style wave')


def classic_scene(day, offset=0):
    index = (day.toordinal() + offset) % len(NAMES)
    colour = tuple(int(c*255) for c in colorsys.hsv_to_rgb(
        (day.toordinal()*.61803398875) % 1, .65, 1))
    header = """def draw_frame(draw, t, audio, width, height):
    strength = audio['pulse'] if audio['quiet'] else audio['level']
    for i in range(12):
"""
    energy = "        energy = strength if audio['quiet'] else min(1, .4*strength+.6*audio['bands'][i*2])\n"
    forms = [energy+"""        x = 25+i*310/12
        h = 12+220*energy+4*math.sin(t*2+i)
        draw.line((x,320,x,320-h), fill=COLOUR, width=12)
""", energy+"""        x = 25+i*310/12
        h = 8+140*energy+3*math.sin(t*2+i)
        draw.line((x,180-h,x,180+h), fill=COLOUR, width=10)
""", energy+"""        angle = i*2*math.pi/12+t*.15
        r = 65+95*energy
        draw.line((180+45*math.cos(angle),180+45*math.sin(angle),180+r*math.cos(angle),180+r*math.sin(angle)), fill=COLOUR, width=10)
""", """        amplitude = 12+135*strength
        x = 20+i*320/12
        next_x = 20+(i+1)*320/12
        y = 180+amplitude*math.sin(i*4*math.pi/12+t*2)
        next_y = 180+amplitude*math.sin((i+1)*4*math.pi/12+t*2)
        draw.line((x,y,next_x,next_y), fill=COLOUR, width=6)
"""]
    return NAMES[index], header+forms[index].replace('COLOUR', repr(colour))
