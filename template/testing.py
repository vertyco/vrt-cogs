from redbot.core import commands


class test:

    # This actually works!

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.test_list = None

    async def test(self):
        print(self.test_list)
        await self.aaa()

    async def addn(self, num):
        self.test_list.append(int(num))
        await self.aaa()
