def draw_frame(draw, t, audio, width, height):
    strength = audio['pulse'] if audio['quiet'] else audio['level']
    for i in range(12):
        angle = i * math.pi / 6 + t * 0.4
        x = 180 + 90 * math.cos(angle)
        y = 15 + i * 320 / 12
        r = 6 + 25 * strength
        draw.ellipse((x-r, y-r, x+r, y+r), fill=(242, 89, 255))
