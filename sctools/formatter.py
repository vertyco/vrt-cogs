import discord


async def ships(data):
    data = data["data"]
    embeds = []
    page = 1
    pages = 0
    for ship in data:
        if not ship:
            continue
        pages += 1
    for ship in data:
        if not ship:
            continue
        afterburner_speed = ship["afterburner_speed"]
        if afterburner_speed:
            afterburner_speed = "{:,}".format(int(afterburner_speed))
            afterburner_speed = f"{afterburner_speed} m/s"
        beam = ship["beam"]
        if beam:
            beam = f"{beam} m"
        cargo_capacity = ship["cargocapacity"]
        chassis_id = ship["chassis_id"]
        description = ship["description"]
        focus = ship["focus"]
        height = ship["height"]
        if height:
            height = f"{height} m"
        length = ship["length"]
        if length:
            length = f"{length} m"
        manufacturer = ship["manufacturer"]["name"]
        mcode = ship["manufacturer"]["code"]
        mdesc = ship["manufacturer"]["description"]
        mass = ship["mass"]
        if mass:
            mass = "{:,}".format(int(mass))
            mass = f"{mass} kg"
        image = ship["media"][0]["source_url"]
        max_crew = ship["max_crew"]
        min_crew = ship["min_crew"]
        name = ship["name"]
        pitch_max = ship["pitch_max"]
        if pitch_max:
            pitch_max = f"{pitch_max} deg/s"
        price = ship["price"]
        if price:
            price = f"{price} USD"
        prod_status = ship["production_status"]
        roll_max = ship["roll_max"]
        if roll_max:
            roll_max = f"{roll_max} deg/s"
        scm_speed = ship["scm_speed"]
        if scm_speed:
            scm_speed = f"{scm_speed} m/s"
        size = ship["size"]
        x_accel = ship["xaxis_acceleration"]
        if x_accel:
            x_accel = f"{x_accel} m/s²"
        yaw_max = ship["yaw_max"]
        if yaw_max:
            yaw_max = f"{yaw_max} deg/s"
        y_accel = ship["yaxis_acceleration"]
        if y_accel:
            y_accel = f"{y_accel} m/s²"
        z_accel = ship["zaxis_acceleration"]
        if z_accel:
            z_accel = f"{z_accel} m/s²"

        embed = discord.Embed(
            title=name,
            description=f"```\n{description}\n```\n"
            f"`Focus:             `{focus}\n"
            f"`Production Status: `{prod_status}\n"
            f"`Price:             `{price}",
            color=discord.Color.random(),
        )
        if image.startswith("/"):
            image = f"https://robertsspaceindustries.com{image}"
        embed.set_image(url=image)
        embed.add_field(
            name="Ship Specs",
            value=f"`Mass:       `{mass}\n"
            f"`Cargo Cap:  `{cargo_capacity}\n"
            f"`Chassis ID: `{chassis_id}\n"
            f"`Min Crew:   `{min_crew}\n"
            f"`Max Crew:   `{max_crew}\n"
            f"`Size:       `{size}\n"
            f"`Height:     `{height}\n"
            f"`Length:     `{length}\n"
            f"`Beam:       `{beam}\n"
            f"`Max Pitch:  `{pitch_max}\n"
            f"`Max Roll:   `{roll_max}\n"
            f"`Max Yaw:    `{yaw_max}",
        )
        embed.add_field(
            name="Thrust Capabilities",
            value=f"`Afterburner Speed: `{afterburner_speed}\n"
            f"`SCM Speed:         `{scm_speed}\n"
            f"`X-Acceleration:    `{x_accel}\n"
            f"`Y-Acceleration:    `{y_accel}\n"
            f"`Z-Acceleration:    `{z_accel}",
        )
        embed.add_field(
            name="Manufacturer",
            value=f"`Name:  `{manufacturer}\n"
            f"`Code:  `{mcode}\n"
            f"```\n{mdesc}\n```",
            inline=False,
        )
        # Detailed component breakdown
        comp_data = ship["compiled"]
        for cname, data in comp_data.items():
            if cname == "RSIAvionic":
                continue
            if cname == "RSIModular":
                cname = "Modules"
            if cname == "RSIPropulsion":
                cname = "Fuel Tanks & Drives"
            if cname == "RSIThruster":
                cname = "Thrusters"
            if cname == "RSIWeapon":
                cname = "Weapons"
            info = ""
            for compname, comp in data.items():
                if comp:
                    if comp[0]["component_size"] == "-":
                        continue
                    if comp[0]["manufacturer"] == "TBD":
                        continue
                    if comp[0]["component_size"] == "TBD":
                        continue
                    compname = compname.replace("_", " ")
                    info += f"**{compname.capitalize()}**\n"
                    for i in comp:
                        size = i["component_size"]
                        manufacturer = i["manufacturer"]
                        name = i["name"]
                        quantity = i["quantity"]
                        info += (
                            f"`Size:  `{size}\n"
                            f"`Mfr:   `{manufacturer}\n"
                            f"`Name:  `{name}\n"
                            f"`Qty:   `{quantity}\n"
                        )
            if info != "":
                embed.add_field(name=cname, value=info, inline=True)
        embed.set_footer(text=f"Page {page}/{pages}")
        page += 1
        embeds.append(embed)
    return embeds
