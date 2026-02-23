// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import com.github.jengelman.gradle.plugins.shadow.tasks.ShadowJar
import java.io.InputStreamReader
import java.io.BufferedReader
import org.gradle.api.tasks.testing.logging.TestExceptionFormat

plugins {
    scala
    application
    id("com.github.johnrengelman.shadow") version "7.1.2"
    id("com.diffplug.spotless") version "6.4.2"
    jacoco
    id("com.github.jk1.dependency-license-report") version "3.1.1"
}

jacoco {
    toolVersion = "0.8.12"
}

dependencies {
    implementation("org.scala-lang:scala-library:2.12.20")
    implementation("com.google.guava:guava:31.1-jre")
    // Use manually built jar with infinity/nan fix and compatible Jackson libraries pinned.
    // See "lib" directory for patch information.
    implementation(files("lib/glow-spark3-assembly-1.2.2-SNAPSHOT.jar"))
    implementation("net.sourceforge.argparse4j:argparse4j:0.+")
    implementation("io.spray:spray-json_2.12:1.3.6")
    // Vendored Omics JAR — contains only service classes, no core SDK.
    implementation(files("lib/AwsJavaSdk-Omics-2.0.jar"))
    // Core SDK + arns: compileOnly for compilation, provided by Glue runtime at execution time
    compileOnly("software.amazon.awssdk:arns:2.17.161")
    compileOnly("software.amazon.awssdk:sdk-core:2.17.161")
    compileOnly("software.amazon.awssdk:aws-core:2.17.161")
    compileOnly("software.amazon.awssdk:url-connection-client:2.17.161")
    implementation("com.fasterxml.jackson.core:jackson-annotations:2.18.1")
    implementation("com.fasterxml.jackson.core:jackson-core:2.18.1")
    implementation("com.fasterxml.jackson.core:jackson-databind:2.18.1")
    compileOnly("org.apache.spark:spark-sql_2.12:3.1.1")
    compileOnly("org.apache.iceberg:iceberg-core:0.14.0")
    compileOnly(files("lib/glue-assembly.jar"))
    constraints {
        implementation("org.apache.logging.log4j:log4j-core") {
            version {
                require("2.17.0")
                because("Older Log4J versions are recalled for security")
            }
        }
        implementation("com.fasterxml.jackson.module:jackson-module-scala_2.12") {
            version {
                strictly("2.10.5")
            }
        }
        implementation("io.netty:netty-all") {
            version {
                require("4.1.100.Final")
                because("Older versions are recalled for security concerns with HTTP/2 Rapid Reset Attack")
            }
        }
    }
    testImplementation(
        "org.apache.spark", "spark-core_2.12", "3.1.1", classifier="tests")
    testImplementation("org.apache.spark:spark-sql_2.12:3.1.1")
    testImplementation(
        "org.apache.spark", "spark-sql_2.12", "3.1.1", classifier="tests")
    testImplementation(
        "org.apache.spark", "spark-catalyst_2.12", "3.1.1", classifier="tests")
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.scalatest:scalatest_2.12:3.2.10")
    testImplementation("org.scalatestplus:junit-4-13_2.12:3.2.2.0")
    testImplementation("com.amazonaws:aws-java-sdk-glue:1.12.196")
    testImplementation(files("lib/glue-assembly.jar"))
    testImplementation("org.mockito:mockito-scala-scalatest_2.12:1.17.5")
    testImplementation("org.mockito:mockito-scala_2.12:1.17.5")
    testRuntimeOnly("org.scala-lang.modules:scala-xml_2.12:1.2.0")
    testRuntimeOnly("org.junit.vintage:junit-vintage-engine:5.8.1")
    // Core SDK needed at test time (provided by Glue runtime in production)
    testImplementation("software.amazon.awssdk:sdk-core:2.17.161")
    testImplementation("software.amazon.awssdk:aws-core:2.17.161")
    testImplementation("software.amazon.awssdk:url-connection-client:2.17.161")
    testImplementation("software.amazon.awssdk:arns:2.17.161")
    // JSON protocol needed at test time for OmicsClient (provided by Glue runtime in production)
    testImplementation("software.amazon.awssdk:aws-json-protocol:2.17.161")
}

licenseReport {
    configurations = arrayOf("runtimeClasspath")
    renderers = arrayOf(com.github.jk1.license.render.InventoryHtmlReportRenderer())
}

spotless {
    scala {
        target("src/**/*.scala")
        scalafmt().configFile(".scalafmt.conf")
    }
}

application {
    // Define the main class for the application.
    mainClass.set("com.amazon.vincent.job.SampleJob")
}

//  glue 3.0 at Java Runtime only recognizes class file versions up to 52.0
java {
    sourceCompatibility = JavaVersion.VERSION_1_8
    targetCompatibility = JavaVersion.VERSION_1_8
}

tasks.compileScala {
    scalaCompileOptions.apply {
        forkOptions.apply {
            memoryMaximumSize = "4g"
        }
    }
}

tasks.register<Copy>("copyConfiguration") {
    from(layout.projectDirectory.dir("configuration"))
    into(layout.buildDirectory)
}

tasks.test {
    // Spark 3.1.1 is incompatible with JDK 17+; fork test execution on JDK 11
    javaLauncher.set(javaToolchains.launcherFor {
        languageVersion.set(JavaLanguageVersion.of(11))
    })
    jvmArgs = listOf(
        "--add-opens=java.base/java.lang=ALL-UNNAMED",
        "--add-opens=java.base/java.lang.invoke=ALL-UNNAMED",
        "--add-opens=java.base/java.lang.reflect=ALL-UNNAMED",
        "--add-opens=java.base/java.io=ALL-UNNAMED",
        "--add-opens=java.base/java.net=ALL-UNNAMED",
        "--add-opens=java.base/java.nio=ALL-UNNAMED",
        "--add-opens=java.base/java.util=ALL-UNNAMED",
        "--add-opens=java.base/java.util.concurrent=ALL-UNNAMED",
        "--add-opens=java.base/java.util.concurrent.atomic=ALL-UNNAMED",
        "--add-opens=java.base/sun.nio.ch=ALL-UNNAMED",
        "--add-opens=java.base/sun.nio.cs=ALL-UNNAMED",
        "--add-opens=java.base/sun.security.action=ALL-UNNAMED",
        "--add-opens=java.base/sun.util.calendar=ALL-UNNAMED",
        "--add-opens=java.security.jgss/sun.security.krb5=ALL-UNNAMED")
}

tasks.named<Test>("test") {
    // spotless check for formatting
    dependsOn("spotlessCheck")
    useJUnitPlatform()
    // Reorder classpath so JUnit 4.13.2 appears before glue-assembly.jar (which bundles 4.11)
    classpath = files(
        configurations.testRuntimeClasspath.get().filter { !it.name.contains("glue-assembly") },
        files("lib/glue-assembly.jar")
    ) + sourceSets.test.get().output + sourceSets.main.get().output
    testLogging {
        showStackTraces = true
        exceptionFormat = TestExceptionFormat.FULL
    }
    finalizedBy(tasks.jacocoTestReport) // report is always generated after tests run
}

// Use Gradle Shadow to create an uberjar for use in the Glue Job
tasks.withType<ShadowJar> {
    // Generate super jar after tests/fmt passes - reduce dev time.
    dependsOn("test")
    archiveBaseName.set("AwsVincentJobs")
    archiveClassifier.set("super")
    archiveVersion.set("")
    isZip64 = true
    dependencies {
        // glue has its own version. We will use it. Log4j in uberjar cause issues with glue
        exclude {
            it.moduleGroup == "org.apache.log4j" || it.moduleGroup == "org.apache.logging.log4j"
        }
    }
}

tasks.getByName("build") {
    dependsOn("copyConfiguration")
}

tasks.register("release") {
    dependsOn("build")
}

tasks.register("upload") {
    val awsAccountId = System.getenv("AWS_ACCOUNT_ID")
    val bucketName = "$awsAccountId-awsvincentjobs-test-jar"
    println("Creating bucket $bucketName if doesn't exist")
    ProcessBuilder("aws", "s3", "mb", "s3://$bucketName")
        .redirectOutput(ProcessBuilder.Redirect.INHERIT)
        .redirectError(ProcessBuilder.Redirect.INHERIT)
        .start()
        .waitFor()
    println("Uploading jar artifact AwsVincentJobs-super.jar to s3://$bucketName")
    ProcessBuilder("aws", "s3", "cp", "build/libs/AwsVincentJobs-super.jar", "s3://$bucketName/")
        .redirectOutput(ProcessBuilder.Redirect.INHERIT)
        .redirectError(ProcessBuilder.Redirect.INHERIT)
        .start()
        .waitFor()
}

tasks.register("runGlue") {
    val awsRegion = "us-west-2"
    val reader = BufferedReader(InputStreamReader(System.`in`))
    // TODO: create a new glue job for manual test
    println("Glue Job name: ")
    val jobName = reader.readLine()
    println("Number of runs: ")
    val numberOfRuns = reader.readLine().toInt()

    // TODO: generate dynamic job id to pass data quality check
    val jsonFile = File("glueParameters.json")
    val jsonString = jsonFile.readText()
    println("Running with parameters:")
    println(jsonString)
    val process = ProcessBuilder("aws", "glue", "start-job-run", "--region", awsRegion, "--job-name", jobName, "--arguments", jsonString)
        .redirectOutput(ProcessBuilder.Redirect.INHERIT)
        .redirectError(ProcessBuilder.Redirect.INHERIT)
    for (i in 0 until numberOfRuns) {
        process.start()
        println("Run ${i+1} started")
    }
}

tasks.jacocoTestReport {
    executionData(tasks.run.get())
    sourceSets(sourceSets.main.get())
    reports {
        xml.required.set(true)
        csv.required.set(true)
        html.required.set(true)
        csv.outputLocation.set(layout.buildDirectory.file("brazil-documentation/coverage/coverage.csv"))
        xml.outputLocation.set(layout.buildDirectory.file("brazil-documentation/coverage/coverage.xml"))
        html.outputLocation.set(layout.buildDirectory.dir("brazil-documentation/coverage/html"))
    }
    dependsOn(tasks.test)
    finalizedBy("generateCoverageDataTxt")
}

tasks.register("generateCoverageDataTxt") {
    data class CoverageData(
        var lineCovered: Double = 0.0,
        var lineMissed: Double = 0.0,
        var branchCovered: Double = 0.0,
        var branchMissed: Double = 0.0,
    ) {
        operator fun plusAssign(coverageLine: CoverageData): Unit {
            lineCovered += coverageLine.lineCovered
            lineMissed += coverageLine.lineMissed
            branchCovered += coverageLine.branchCovered
            branchMissed += coverageLine.branchMissed
        }

        fun getPercentage(covered: Double, missed: Double) = (covered / (covered + missed)) * 100.0

        fun getLinePercent() = getPercentage(lineCovered, lineMissed)

        fun getBranchPercent() = getPercentage(branchCovered, branchMissed)
    }

    fun extractCoverage(csvFile: String): CoverageData {
        val overallCov = CoverageData()
        File(csvFile).useLines { lines ->
            // skip header
            lines.drop(1).filter { it.isNotBlank() }.forEach { line ->
                val fields = line.split(',')
                val (branchMissed, branchCovered, lineMissed, lineCovered) = fields.slice(5..8).map { it.toDouble() }
                val coverageData = CoverageData(lineCovered, lineMissed, branchCovered, branchMissed)
                overallCov += coverageData
            }
        }
        return overallCov
    }

    fun writeCoverageDataTxt(coverageData: CoverageData, outFilePath: String) {
        File(outFilePath).printWriter().use { out ->
            out.println("scala:line:${coverageData.getLinePercent()}")
            out.println("scala:branch:${coverageData.getBranchPercent()}")
        }
    }

    dependsOn(tasks.jacocoTestReport)
    doLast {
        val covdir = "${project.buildDir}/generated-make"
        File(covdir).mkdir()
        val coverageData = extractCoverage("${project.buildDir}/brazil-documentation/coverage/coverage.csv")
        writeCoverageDataTxt(coverageData, "$covdir/coverage-data.txt")
    }
}

defaultTasks("release")