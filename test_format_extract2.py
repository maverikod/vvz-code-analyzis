class Base:
    """Base class with common functionality."""

    def __init__(self):
        self.prop1 = None

    def common_method(self):
        return "child1"


class Child1(Base):
    def __init__(self):
        pass

    def specific_method1(self):
        return "specific1"


class Child2(Base):
    def __init__(self):
        pass

    def specific_method1(self):
        return "specific1"
