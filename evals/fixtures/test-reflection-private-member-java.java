import java.lang.reflect.Method;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

public class SurchargeCalculatorTest {

    @Test
    public void computesSurchargeMultiplierViaReflection() throws Exception {
        SurchargeCalculator calculator = new SurchargeCalculator();

        // No public method exposes this standalone computation on its own --
        // it's buried inside a much larger public workflow. The test reaches
        // around encapsulation via reflection instead of extracting the
        // computation into its own testable collaborator.
        Method method = SurchargeCalculator.class.getDeclaredMethod(
                "computeSurchargeMultiplier", int.class);
        method.setAccessible(true);

        double multiplier = (double) method.invoke(calculator, 12);

        assertEquals(1.12, multiplier, 0.0001);
    }
}
