def draw_frame(draw, t, audio, width, height):
    t = t * 1.2 + 0.0
    strength = audio['pulse'] if audio['quiet'] else audio['level']
    for i in range(8):
        energy = min(1, 1.0 * (strength if audio['quiet'] else .6*strength+.4*audio['bands'][i*3]))
        angle = i*math.pi/4+t*.15
        r = 60+60*energy+25*math.sin(t+i)
        draw.line((180,180,180+r*math.cos(angle),180+r*math.sin(angle)), fill=(255, 145, 89), width=6)
