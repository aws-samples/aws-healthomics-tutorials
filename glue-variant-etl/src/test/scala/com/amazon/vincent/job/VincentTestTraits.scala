// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job

import com.amazon.vincent.job.logger.LoggerTrait
import com.amazon.vincent.job.models.vep.VepEntry
import com.amazon.vincent.job.models.{AnnotationFields, Schema, StoreFormat}
import com.amazonaws.SDKGlobalConfiguration
import org.apache.log4j.Logger
import org.apache.spark.sql.types.StructType
import org.apache.spark.sql.{DataFrame, Row, SparkSession}
import org.scalatest.{BeforeAndAfterAll, Suite}
import software.amazon.awssdk.regions.Region

import java.io.{File, FileWriter}
import scala.collection.mutable.ArrayBuffer

trait VincentTestTraits

trait VincentTestSuite {
  this: Suite =>

  protected implicit def testVincentLogger: LoggerTrait = new LoggerTrait {
    private val logger = Logger.getLogger("VincentTestLogger")

    override def info(m: String): Unit = logger.info(m)

    override def error(m: String): Unit = logger.error(m)

    override def warn(m: String): Unit = logger.warn(m)
  }

  val testVCFFile: String = "./src/test/resources/variants.vcf"
  val testJobName: String = "515897426285-d1a56aaf5204-variant"
  val testDatabaseName = "515897426285-d1a56aaf5204-variant"
  val testTableName = "test_base_store"
  val testTablePath = "s3://515897426285-1e35f015-8783-497c-966a-093e6cff9b2e-909131341361/omics"
  val testTableFormat = "iceberg_0"
  val testJobId = "515897426285_dd624175-89c9-4be7-950b-669f293bafcb_0_4_1"
  val testInputPath =
    "s3://analytics-test-assets-ap-southeast-1/variants.vcf.gz"
  val testReferenceArn =
    "arn:aws:omics:ap-southeast-1:515897426285:referenceStore/5462579941/reference/2511358047"
  val testRunLeftNormalization = "false"
  val testFormatOptions = "{}"
  val testStoreOptions = "{}"
  val testStoreFormat: StoreFormat = StoreFormat.VCF
  val testStoreFormatName: String = testStoreFormat.name
  val testAnnotationFields = new AnnotationFields(vep = Some("CSQ"))
  val testAnnotationFieldsJsonString = """{"VEP": "CSQ"}"""
  val testInfoCSQValue =
    "T|intron_variant&non_coding_transcript_variant|MODIFIER|ANKEF1|,T|downstream_gene_variant|MODIFIER|SNAP25-AS1|TFA"
  val testTableSortKeys = Nil

  val testExpectedVepEntries = List(
    VepEntry(
      allele = Some("T"),
      consequence = Some(Array("intron_variant", "non_coding_transcript_variant")),
      impact = Some("MODIFIER"),
      symbol = Some("ANKEF1"),
      extras = Some(Map("transcription_factors" -> ""))),
    VepEntry(
      allele = Some("T"),
      consequence = Some(Array("intron_variant", "non_coding_transcript_variant")),
      impact = Some("MODIFIER"),
      symbol = Some("SNAP25-AS1"),
      extras = Some(Map("transcription_factors" -> "TFA"))))

  val testVCFRowData = Seq(
    testJobId,
    "chr3",
    63912683,
    63912684,
    null,
    "G",
    ArrayBuffer("T"),
    10.0,
    ArrayBuffer("PASS"),
    false,
    Map("CSQ" -> testInfoCSQValue, "VARID" -> "ATXN7"),
    false,
    ArrayBuffer(0, 0),
    null,
    null,
    null,
    null,
    null,
    null,
    null,
    "HG0001",
    null)

  val testVCFFileRows = Seq(
    Row(
      testJobId,
      "chr3",
      63912683,
      63912684,
      null,
      "G",
      List("T"),
      10.0,
      List("PASS"),
      false,
      Map("CSQ" -> testInfoCSQValue, "VARID" -> "ATXN7"),
      false,
      ArrayBuffer(0, 0),
      null,
      null,
      null,
      null,
      null,
      null,
      null,
      "HG0001",
      null),
    Row(
      testJobId,
      "chr3",
      63912683,
      63912684,
      null,
      "G",
      List("T"),
      10.0,
      List("PASS"),
      false,
      Map("CSQ" -> testInfoCSQValue, "VARID" -> "ATXN7"),
      false,
      List(1, 0),
      null,
      null,
      null,
      null,
      null,
      null,
      null,
      "HG0002",
      null))

  def createTestVCFDataFrame(
      spark: SparkSession,
      expectedRows: Seq[Row] = testVCFFileRows,
      schema: StructType = Schema.VariantSchemaWithInfo): DataFrame = {
    spark.createDataFrame(spark.sparkContext.parallelize(expectedRows), schema)
  }

  def createRowData(calls: List[Int]): Unit = {
    Row(
      testJobId,
      "chr3",
      63912683,
      63912684,
      null,
      "G",
      List("T"),
      10.0,
      List("PASS"),
      false,
      Map("CSQ" -> testInfoCSQValue, "VARID" -> "ATXN7"),
      false,
      List(0, 0),
      null,
      null,
      null,
      null,
      null,
      null,
      null,
      "HG0001",
      null)

  }

  def withTempFile(prefix: String, suffix: String, testCode: (File, FileWriter) => Any): Unit = {
    val file = File.createTempFile(prefix, suffix) // create the fixture
    val writer = new FileWriter(file)
    try {
      testCode(file, writer) // "loan" the fixture to the test
    } finally writer.close() // clean up the fixture
  }
}

/**
 * A trait that setup system properties during beforeAll/beforeEach
 *
 * Currently, we only use it for AWS_REGION for our sdk client.
 */
trait TestSysProp extends BeforeAndAfterAll { this: Suite =>

  var awsRegion: Option[String] = None

  // set AWS_REGION_ENV_VAR when region information is not found in the environment (i.e coverlay)
  override def beforeAll(): Unit = {
    awsRegion = sys.props.get(SDKGlobalConfiguration.AWS_REGION_SYSTEM_PROPERTY)
    sys.props.+=((SDKGlobalConfiguration.AWS_REGION_SYSTEM_PROPERTY, Region.US_WEST_2.toString))
    super.beforeAll()
  }

  override def afterAll(): Unit = {
    awsRegion match {
      case Some(value) => sys.props.+=((SDKGlobalConfiguration.AWS_REGION_SYSTEM_PROPERTY, value))
      case None => sys.props.-=(SDKGlobalConfiguration.AWS_REGION_SYSTEM_PROPERTY)
    }
    super.afterAll()
  }
}
