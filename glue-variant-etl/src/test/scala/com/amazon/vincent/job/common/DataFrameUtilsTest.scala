// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.common

import com.amazon.vincent.job.common.DataFrameUtils.processSparkException
import com.amazon.vincent.job.models.exceptions.VincentUserException
import htsjdk.tribble.TribbleException
import org.apache.spark.SparkException
import org.apache.spark.sql.{DataFrame, QueryTest}
import org.apache.spark.sql.test.SharedSparkSession
import org.junit.runner.RunWith
import org.mockito.MockitoSugar.{mock, when}
import org.scalatest.BeforeAndAfterEach
import org.scalatestplus.junit.JUnitRunner

@RunWith(classOf[JUnitRunner])
class DataFrameUtilsTest extends QueryTest with BeforeAndAfterEach with SharedSparkSession {
  import testImplicits._

  var mockDF: DataFrame = _
  val tribbleMsg = "tribble msg"
  val dfName: String = "mockTable"
  val returnedExceptionMsg = "Malformed Input. Please check content of input file."
  val testTribbleExceptionMsg = "test exception message"
  val testSparkExceptionMsg = "User Data Error"

  override def beforeEach(): Unit = {
    mockDF = mock[DataFrame]
    super.beforeEach()
  }

  test("make sure extra cols goes to a information column") {
    val df = Seq(("chr1", 1, 10, "20"), ("chr2", 10, 20, "30"), ("chr2", 20, 30, "40")).toDF(
      "chrom",
      "start",
      "extra1",
      "extra2")

    val extraCols = List("extra1", "extra2")

    val transformed = DataFrameUtils.addExtraColsToInformationCol(df, extraCols, "info")

    val expected = Seq(
      ("chr1", 1, Map("extra1" -> "10", "extra2" -> "20")),
      ("chr2", 10, Map("extra1" -> "20", "extra2" -> "30")),
      ("chr2", 20, Map("extra1" -> "30", "extra2" -> "40"))).toDF("chrom", "start", "info")
    checkAnswer(transformed, expected)
  }

  test("Tribble Exception Gets Caught") {
    val sparkException =
      new SparkException(
        testSparkExceptionMsg,
        cause = new TribbleException(testTribbleExceptionMsg))

    when(mockDF.writeTo(dfName)).thenThrow(sparkException)
    val caught =
      intercept[VincentUserException](DataFrameUtils.appendDF(mockDF, dfName, Nil))
    assertResult(caught.getMessage)(returnedExceptionMsg)
  }

  test("Cyclic exceptions get caught") {
    val exceptionA = new Exception()
    val exceptionB = new Exception(exceptionA)
    val exceptionC = new Exception(exceptionB)
    exceptionA.initCause(exceptionC)

    val sparkException = new SparkException(testSparkExceptionMsg, exceptionA)
    when(mockDF.writeTo(dfName)).thenThrow(sparkException)
    val caught =
      intercept[SparkException](DataFrameUtils.appendDF(mockDF, dfName, Nil))
    assertResult(caught.getMessage)(testSparkExceptionMsg)
  }

  test("Non TribbleException return original exception message") {
    val exceptionA = new Exception()
    val exceptionB = new Exception(exceptionA)
    val sparkException = new SparkException(testSparkExceptionMsg, exceptionB)
    when(mockDF.writeTo(dfName)).thenThrow(sparkException)
    val caught =
      intercept[SparkException](DataFrameUtils.appendDF(mockDF, dfName, Nil))
    assertResult(caught.getMessage)(testSparkExceptionMsg)
  }

  test("Insufficient column in vcf") {
    val df = spark.read
      .format(source = "vcf")
      .option("flattenInfoFields", "False")
      .option("validationStrigency", "Strict")
      .load("./src/test/resources/data/missing_column.vcf")

    val caught = intercept[SparkException] {
      df.collect()
    }
    val vincentException = intercept[VincentUserException] {
      processSparkException(caught)
    }
    assertResult(vincentException.getMessage)("Line 28: there aren't enough columns for line")
  }

  test("Issue with unparsable alleles") {
    val df = spark.read
      .format(source = "vcf")
      .option("flattenInfoFields", "False")
      .option("validationStrigency", "Strict")
      .load("./src/test/resources/data/wrong_allele.vcf")

    val caught = intercept[SparkException] {
      df.collect()
    }
    val vincentException = intercept[VincentUserException] {
      processSparkException(caught)
    }
    assertResult(vincentException.getMessage)(
      "The provided VCF file is malformed at approximately line number 29: unparsable vcf record with allele")
  }

  test("Issue with unsupported allele data") {
    val df = spark.read
      .format(source = "vcf")
      .option("flattenInfoFields", "False")
      .option("validationStrigency", "Strict")
      .load("./src/test/resources/data/unsupported_allele.vcf")

    val caught = intercept[SparkException] {
      df.collect()
    }
    val vincentException = intercept[VincentUserException] {
      processSparkException(caught)
    }
    assertResult(vincentException.getMessage)(
      "The provided VCF file is malformed at approximately line number 29")
  }

  test("IA Exception gets caught with error match") {
    val exceptionA = new IllegalArgumentException(
      "Key VARID found in field INFO but isn't defined in the VCFHeader.")
    val exceptionB = new Exception(exceptionA)
    val sparkException = new SparkException(testSparkExceptionMsg, exceptionB)
    when(mockDF.writeTo(dfName)).thenThrow(sparkException)
    val caught =
      intercept[VincentUserException](DataFrameUtils.appendDF(mockDF, dfName, Nil))
    assertResult(caught.getMessage)("Key found in field INFO but isn't defined in the VCFHeader.")
  }

  test("IA Exception gets caught") {
    val exceptionA = new IllegalArgumentException("unknown error")
    val exceptionB = new Exception(exceptionA)
    val sparkException = new SparkException(testSparkExceptionMsg, exceptionB)
    when(mockDF.writeTo(dfName)).thenThrow(sparkException)
    val caught =
      intercept[SparkException](DataFrameUtils.appendDF(mockDF, dfName, Nil))
    assertResult(caught.getMessage)(testSparkExceptionMsg)
  }

}
