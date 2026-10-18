def draw_frame(draw, t, audio, width, height):
    strength = audio['level']
    for i in range(8):
        energy = min(1, .6*strength+.4*audio['bands'][i*3])
        x = 180 + (40 + 80 * energy) * math.sin(t * 3.1 + i * 3.1 + i)
        y = 180 + (40 + 80 * energy) * math.cos(t * 3.1 + i * 3.1 + i)
        r = 8 + 40 * energy
        angle = math.cos(energy)
        colour = (128, 128, 128)
        draw.ellipse((x-r,y-r,x+r,y+r), outline=colour, width=4)
