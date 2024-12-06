from .tables import AppealQuestion


class DBUtils:
    async def get_sorted_questions(self, guild_id: int) -> list[AppealQuestion]:
        return (
            await AppealQuestion.objects()
            .where(AppealQuestion.guild == guild_id)
            .order_by(AppealQuestion.sort_order, AppealQuestion.created_at)
        )
