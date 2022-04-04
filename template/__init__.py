from .template import Template

___red_end_user_data_statement__ = (
    "End User Statement"
)


def setup(bot):
    bot.add_cog(Template(bot))
