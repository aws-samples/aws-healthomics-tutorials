package script

/*
 * Glue jobs require a script, even if we're not using it
 * (for the entry-point class, we give Glue a class name
 * from a dependent JAR)
 */
object DummyScript
