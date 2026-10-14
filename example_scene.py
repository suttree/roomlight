def draw_frame(draw, t, audio, width, height):
    draw.rectangle((0, 0, width, height), fill=(8, 14, 25))
    strength = audio['pulse'] * 0.3 if audio['quiet'] else audio['level']
    for i in range(18):
        a = i * math.tau / 18 + t * 0.18
        band = audio['bands'][i]
        orbit = 75 + 22 * math.sin(t * 0.6 + i * 0.3) + 35 * strength
        x = width / 2 + math.cos(a) * orbit
        y = height / 2 + math.sin(a) * orbit
        r = 3 + band * 12 + strength * 4
        draw.ellipse((x-r, y-r, x+r, y+r), fill=(60, 150 + i * 5, 205))
