"""Test file for split with formatting."""


class LargeClass:
    """A large class that needs to be split."""

    def __init__(self):
        self.classA = ClassA()
        self.classB = ClassB()
        self.classC = ClassC()

    def method1(self):
        return self.classA.method1()

    def method2(self):
        return self.classB.method2()

    def method3(self):
        return self.classC.method3()


class ClassA:
    """A large class that needs to be split."""

    def __init__(self):
        self.prop1 = None

    def method1(self):
        """First method."""
        return "method1"


class ClassB:
    """A large class that needs to be split."""

    def __init__(self):
        self.prop2 = None

    def method2(self):
        """Second method."""
        return "method2"


class ClassC:
    """A large class that needs to be split."""

    def __init__(self):
        self.prop3 = None

    def method3(self):
        """Third method."""
        return "method3"
