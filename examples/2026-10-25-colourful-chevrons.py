def draw_frame(draw, t, audio, width, height):
    strength = audio['level']
    for i in range(8):
        energy = min(1, .6*strength+.4*audio['bands'][i*3])
        x = 180 + 120 * math.cos(t - 2.3 * i + i)
        y = 180 + 120 * math.sin(t - 2.3 * i + i)
        r = 8 + 40 * energy
        angle = 2.3 * i + i
        colour = ((255, 88, 40), (255, 192, 40), (224, 48, 136), (112, 64, 240))[i % 4]
        draw.line((x-r,y-r,x,y+r,x+r,y-r*.4), fill=colour, width=8)
