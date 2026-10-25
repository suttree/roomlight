def draw_frame(draw, t, audio, width, height):
    level = min(1, max(0, audio['level']))
    for i in range(24):
        band = min(1, max(0, audio['bands'][i]))
        h = 250 * band * (.65 + .35 * level)
        x = 14 + i * 14
        colour = (int(145+110*math.cos(i*.22)), int(145+110*math.cos(i*.22-2.1)), int(145+110*math.cos(i*.22-4.2)))
        for j in range(8):
            bottom = 300-j*31
            top = max(300-h, bottom-27)
            if top < bottom:
                draw.rectangle((x,top,x+9,bottom), fill=colour)
        if h > 2:
            draw.line((x,296-h,x+9,296-h), fill=(235,245,255), width=2)
    draw.line((14,309,345,309), fill=(35,45,65), width=1)
    for i in range(24):
        colour = (40,220,160) if i < 16 else (255,180,40) if i < 21 else (255,65,100)
        if i/24 < level:
            draw.rectangle((14+i*14,327,23+i*14,338), fill=colour)
