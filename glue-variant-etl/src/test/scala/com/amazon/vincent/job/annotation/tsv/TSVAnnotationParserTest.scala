// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.annotation.tsv

import com.amazon.vincent.job.common.DataFrameUtils
import com.amazon.vincent.job.models.exceptions.VincentUserException
import org.apache.spark.SparkException
import org.apache.spark.sql.test.SharedSparkSession
import org.apache.spark.sql.{QueryTest, Row}
import org.junit.runner.RunWith
import org.mockito.ArgumentMatchers.any
import org.mockito.Mockito
import org.mockito.Mockito.{never, times, verify}
import org.scalatestplus.junit.JUnitRunner

import java.io.{File, FileWriter}

@RunWith(classOf[JUnitRunner])
class TSVAnnotationParserTest extends QueryTest with SharedSparkSession {

  val reference = Reference("src/test/resources/references/test.fasta")
  def withFile(testCode: (File, FileWriter) => Any) {
    val file = File.createTempFile("random", ".tsv") // create the fixture
    val writer = new FileWriter(file)
    try {
      testCode(file, writer) // "loan" the fixture to the test
    } finally writer.close() // clean up the fixture
  }

  test("Load DataFrame with config") {
    val header = List("chrom", "start", "end")
    // make sure that header is renamed correctly
    val content = List("chr1", 0, 10)
    val sparkOptions = Map("header" -> "true", "sep" -> ",")
    val annotationType = AnnotationType.ChrStartEndZeroBase

    // ensure that mapping is done to renamed column
    val formatHeader: FormatHeader =
      FormatHeader(Map("CHR" -> "chr", "START" -> "start", "END" -> "end"), annotationType)

    withFile { (file, writer) =>
      // write input data with original header
      writer.write(s"${header.mkString(",")}\n${content.mkString(",")}")
      writer.flush()
      val tsvParserConfig = new TSVParserConfig(
        inputFile = file.getAbsolutePath,
        schema = "chr STRING, start LONG, end LONG",
        sparkOptions = sparkOptions,
        annotationType = annotationType,
        formatHeader = Some(formatHeader))
      val tsvAnnotationParser = TSVAnnotationParser(tsvParserConfig, spark)
      val df = tsvAnnotationParser.loadDataFrame()
      checkAnswer(df, Row(content: _*) :: Nil)
    }
  }

  test("Throw exception when loading invalid type of content from tsv") {
    val header = List("chrom", "pos")
    val content = List("chr1", "abc") // Invalid String type for pos: Long
    withFile { (file, writer) =>
      writer.write(s"${header.mkString("\t")}\n${content.mkString("\t")}")
      writer.flush()
      val tsvParserConfig = new TSVParserConfig(
        file.getAbsolutePath,
        schema = "chrom STRING, pos LONG",
        annotationType = AnnotationType.ChrPos,
        formatHeader = Some(FormatHeader(contigName = "chrom", start = "pos")),
        reference = Some(reference))
      val tsvAnnotationParser = TSVAnnotationParser(tsvParserConfig, spark)
      val df = tsvAnnotationParser.loadDataFrame()
      // Spark has lazy evaluation until action on dataframe is called
      val caught = intercept[SparkException](df.show())
      val caught2 = intercept[VincentUserException](DataFrameUtils.processSparkException(caught))
      assertResult(
        "Malformed Input. Please check the content and corresponding data type in input file.")(
        caught2.getMessage)
    }
  }

  test("Unstructured dataframe gets process as it is") {
    val header = "header"
    val content = "is-unstructured"
    withFile { (file, writer) =>
      writer.write(s"$header\n$content")
      writer.flush()
      val tsvParserConfig =
        new TSVParserConfig(inputFile = file.getAbsolutePath, schema = "header STRING")
      val tsvAnnotationParser = TSVAnnotationParser(tsvParserConfig, spark)
      val spyTSV = Mockito.spy(tsvAnnotationParser)
      val df = spyTSV.process()
      verify(spyTSV, times(0)).processAnnotation(any())
      checkAnswer(df, Row(content) :: Nil)
    }
  }

  test("ChrPosRefAlt get transformed to correct format and get left normalized") {
    val header = List("chrom", "pos", "ref", "alt")
    val content = List("chr1", 1, "ATGC", "ATAC")
    val expected = Row("chr1", 2, 3, "G", "A") :: Nil
    withFile { (file, writer) =>
      writer.write(s"${header.mkString("\t")}\n${content.mkString("\t")}")
      writer.flush()
      val tsvParserConfig = new TSVParserConfig(
        file.getAbsolutePath,
        schema = "chrom STRING, pos LONG, ref STRING, alt STRING",
        annotationType = AnnotationType.ChrPosRefAlt,
        formatHeader =
          Some(FormatHeader(contigName = "chrom", start = "pos", ref = "ref", alt = "alt")),
        reference = Some(reference),
        runLeftNormalization = true)
      val tsvAnnotationParser = TSVAnnotationParser(tsvParserConfig, spark)
      val spyTSV = Mockito.spy(tsvAnnotationParser)
      val df = spyTSV.process()
      // called thrice, ChrPosRefAlt -> ChrStartEndRefAltOneBased -> ChrStartEndRefAltZeroBased
      verify(spyTSV, times(3)).convertToZeroBaseHalfEnd(any())
      verify(spyTSV, times(1)).leftNormalize(any())
      checkAnswer(df.select("chrom", "pos", "end", "ref", "alt"), expected)
    }
  }

  test("ChrPosRefAlt get transformed to correct format and skip left normalized") {
    val header = List("chrom", "pos", "ref", "alt")
    val content = List("chr1", 1, "ATGC", "ATAC")
    val expected = Row("chr1", 0, 4, "ATGC", "ATAC") :: Nil
    withFile { (file, writer) =>
      writer.write(s"${header.mkString("\t")}\n${content.mkString("\t")}")
      writer.flush()
      val tsvParserConfig = new TSVParserConfig(
        file.getAbsolutePath,
        schema = "chrom STRING, pos LONG, ref STRING, alt STRING",
        annotationType = AnnotationType.ChrPosRefAlt,
        formatHeader =
          Some(FormatHeader(contigName = "chrom", start = "pos", ref = "ref", alt = "alt")),
        reference = Some(reference))
      val tsvAnnotationParser = TSVAnnotationParser(tsvParserConfig, spark)
      val spyTSV = Mockito.spy(tsvAnnotationParser)
      val df = spyTSV.process()
      // called thrice, ChrPosRefAlt -> ChrStartEndRefAltOneBased -> ChrStartEndRefAltZeroBased
      verify(spyTSV, times(3)).convertToZeroBaseHalfEnd(any())
      verify(spyTSV, times(0)).leftNormalize(any())
      checkAnswer(df.select("chrom", "pos", "end", "ref", "alt"), expected)
    }
  }

  test("ChrPos get transformed to correct format gets validated but not left normalized") {
    val header = List("chrom", "pos")
    val content = List("chr1", 1)
    // we use 1 here to ensure make sure that the new column added, 0 will be treated as int instead of float
    val expected = Row("chr1", 0, 1) :: Nil
    withFile { (file, writer) =>
      writer.write(s"${header.mkString("\t")}\n${content.mkString("\t")}")
      writer.flush()
      val tsvParserConfig = new TSVParserConfig(
        file.getAbsolutePath,
        schema = "chrom STRING, pos LONG",
        annotationType = AnnotationType.ChrPos,
        formatHeader = Some(FormatHeader(contigName = "chrom", start = "pos")),
        reference = Some(reference))
      val tsvAnnotationParser = TSVAnnotationParser(tsvParserConfig, spark)
      val spyTSV = Mockito.spy(tsvAnnotationParser)
      val df = spyTSV.process()
      // called thrice, ChrPos -> ChrStartEndOneBased -> ChrStartEndZeroBased
      verify(spyTSV, times(3)).convertToZeroBaseHalfEnd(any())
      verify(spyTSV, never()).leftNormalize(any())
      checkAnswer(df, expected)
    }
  }

}

@RunWith(classOf[JUnitRunner])
class ConvertZeroBaseHalfEndTest extends QueryTest with SharedSparkSession {
  import testImplicits._

  val tsvAnnotationParser =
    TSVAnnotationParser(TSVParserConfig("", ""), spark)
  val reference = Some(Reference("src/test/resources/references/test.fasta"))

  def checkResult(annotation: Annotation, expectedRows: List[Row]): Unit = {
    checkAnswer(annotation.dataFrame, expectedRows)
    assert(annotation.annotationType.isInstanceOf[AnnotationType.ZeroBase])
  }

  test("ConvertZeroBaseHalfEnd converts ChrPos") {

    val annotation =
      Annotation(
        Seq(("chr1", 1), ("chr2", 10), ("chr2", 20)).toDF("chrom", "start"),
        AnnotationType.ChrPos,
        reference = reference)
    val expected = Row("chr1", 0, 1) :: Row("chr2", 9, 10) :: Row("chr2", 19, 20) :: Nil
    checkResult(tsvAnnotationParser.convertToZeroBaseHalfEnd(annotation), expected)
  }

  test("ConvertZeroBaseHalfEnd converts ChrPosRefAlt") {
    val annotation = Annotation(
      Seq(("chr2", 10, "ATG", "A"), ("chr2", 20, "T", "A"))
        .toDF("chrom", "start", "ref", "alt"),
      AnnotationType.ChrPosRefAlt,
      reference = reference)

    // end columns is added at the right of the table
    val expected = Row("chr2", 9, "ATG", "A", 12) :: Row("chr2", 19, "T", "A", 20) :: Nil
    checkResult(tsvAnnotationParser.convertToZeroBaseHalfEnd(annotation), expected)
  }

  test("ConvertZeroBaseHalfEnd converts ChrStartEndRefAltOneBase") {
    val annotation = Annotation(
      Seq(("chr2", 10, 12, "ATG", "A"), ("chr2", 20, 20, "T", "A"))
        .toDF("chrom", "start", "end", "ref", "alt"),
      AnnotationType.ChrStartEndRefAltOneBase,
      reference = reference)
    val expected = Row("chr2", 9, 12, "ATG", "A") :: Row("chr2", 19, 20, "T", "A") :: Nil
    checkResult(tsvAnnotationParser.convertToZeroBaseHalfEnd(annotation), expected)
  }

  test("ConvertZeroBaseHalfEnd converts ChrStartEndOneBase") {
    val annotation = Annotation(
      Seq(("chr2", 10, 12), ("chr2", 20, 20)).toDF("chrom", "start", "end"),
      AnnotationType.ChrStartEndOneBase,
      reference = reference)
    val expected = Row("chr2", 9, 12) :: Row("chr2", 19, 20) :: Nil
    checkResult(tsvAnnotationParser.convertToZeroBaseHalfEnd(annotation), expected)
  }

  test("ConvertZeroBaseHalfEnd does not transform ChrStartEndZeroBase") {
    val annotation = Annotation(
      Seq(("chr2", 9, 12), ("chr2", 19, 20)).toDF("chrom", "start", "end"),
      AnnotationType.ChrStartEndZeroBase,
      reference = reference)
    val expected = Row("chr2", 9, 12) :: Row("chr2", 19, 20) :: Nil
    checkResult(tsvAnnotationParser.convertToZeroBaseHalfEnd(annotation), expected)
  }

  test("ConvertZeroBaseHalfEnd does not transform ChrStartEndRefAltZeroBase") {
    val annotation = Annotation(
      Seq(("chr2", 9, 12, "ATG", "A"), ("chr2", 19, 20, "T", "A"))
        .toDF("chrom", "start", "end", "Ref", "Alt"),
      AnnotationType.ChrStartEndRefAltZeroBase,
      reference = reference)
    val expected = Row("chr2", 9, 12, "ATG", "A") :: Row("chr2", 19, 20, "T", "A") :: Nil
    checkResult(tsvAnnotationParser.convertToZeroBaseHalfEnd(annotation), expected)
  }
}

@RunWith(classOf[JUnitRunner])
class LeftNormalizerTest extends QueryTest with SharedSparkSession {
  import testImplicits._

  test("Ensure left normalization works with custom headers") {
    val tsvAnnotationParser = TSVAnnotationParser(TSVParserConfig("", ""), spark)

    val reference = Some(Reference("src/test/resources/references/test.fasta"))
    val colNames = List("chromosome", "start", "end", "reference", "alt")
    val formatHeader = FormatHeader(
      contigName = colNames.head,
      start = colNames(1),
      end = colNames(2),
      ref = colNames(3),
      alt = colNames(4))
    val df = Seq(("chr1", 0, 4, "ATGC", "ATAC")).toDF(colNames: _*)
    val expected = Row("chr1", 2, 3, "G", "A") :: Nil
    val annotation =
      Annotation(df, AnnotationType.ChrStartEndRefAltZeroBase, formatHeader, reference)
    val actualDF = tsvAnnotationParser.leftNormalize(annotation).dataFrame
    checkAnswer(actualDF, expected)
  }
}
