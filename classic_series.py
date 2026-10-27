"""A permanent daily rotation of audio-driven classic visualisers."""
import datetime

START = datetime.date(2026, 10, 26)
NAMES = ('full-height rainbow spectrum', 'mirrored rainbow equaliser',
         'horizontal rainbow spectrum', 'split rainbow equaliser')


def scheduled_scene(day):
    index = (day - START).days % len(NAMES)
    header = '''def draw_frame(draw, t, audio, width, height):
    level = min(1, max(0, audio['level']))
    for i in range(24):
        band = min(1, max(0, audio['bands'][i]))
        energy = min(1, math.sqrt(band) * (.8 + .2 * level))
        colour = (int(145+110*math.cos(i*.22)), int(145+110*math.cos(i*.22-2.1)), int(145+110*math.cos(i*.22-4.2)))
        x = 6 + i * 14.5
'''
    bodies = (
'''        h = 308 * energy
        if h > 1:
            draw.rectangle((x,320-h,x+11,320), fill=colour)
            draw.line((x,316-h,x+11,316-h), fill=(235,245,255), width=2)
''',
'''        h = 146 * energy
        if h > 1:
            draw.rectangle((x,164-h,x+11,164+h), fill=colour)
            draw.line((x,160-h,x+11,160-h), fill=(235,245,255), width=2)
            draw.line((x,168+h,x+11,168+h), fill=(235,245,255), width=2)
''',
'''        h = 340 * energy
        y = 8 + i * 13
        if h > 1:
            draw.rectangle((8,y,8+h,y+10), fill=colour)
            draw.line((12+h,y,12+h,y+10), fill=(235,245,255), width=2)
''',
'''        h = 146 * energy
        if h > 1:
            draw.rectangle((x,158-h,x+11,158), fill=colour)
            draw.rectangle((x,170,x+11,170+h), fill=colour)
            draw.line((x,154-h,x+11,154-h), fill=(235,245,255), width=2)
''')
    return NAMES[index], header + bodies[index]
