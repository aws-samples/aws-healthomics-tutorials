// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.annotation.tsv

import com.amazon.vincent.job.common.DataFrameUtils
import com.amazon.vincent.job.models.exceptions.VincentUserException
import io.projectglow.common.VariantSchemas._
import io.projectglow.functions.normalize_variant
import io.projectglow.transformers.normalizevariants.VariantNormalizer.{
  changedFieldName,
  normalizationResultFieldName,
  normalizationStatusFieldName
}
import org.apache.spark.SparkException
import org.apache.spark.sql.functions._
import org.apache.spark.sql.{DataFrame, SparkSession}

/**
 * Main class for parsing TSV
 *
 * Specifically, it will
 *
 *   - load tsv files into spark dataframe (`loadDataFrame`)
 *   - For unstructured data, it return the dataframe as it is
 *     - For structured data, it will
 *       - Convert to Zerobase
 *       - Do left normalization if required
 *       - Validate with reference sequence
 *
 * @param tsvParserConfig
 *   TSVParser config containing configurations required for loading and processing
 * @param sparkSession
 *   SparkSession object. This is added as a parameter so we can switch between glue/local spark
 *   instances
 */
case class TSVAnnotationParser(tsvParserConfig: TSVParserConfig, sparkSession: SparkSession) {

  def loadDataFrame(): DataFrame = {
    sparkSession.read
      .format("csv")
      .options(tsvParserConfig.sparkOptions)
      .schema(schemaString = tsvParserConfig.schema)
      .option("mode", "FAILFAST")
      .load(tsvParserConfig.inputFile)
  }

  /**
   * main method that will load dataframe and process it accordingly
   *
   * @return
   *   processed dataframe
   */
  def process(): DataFrame = {
    val df = loadDataFrame()
    val inputAnnotationType = tsvParserConfig.annotationType
    inputAnnotationType match {
      case annotationType: AnnotationType.StructuredAnnotation =>
        val annotation =
          Annotation(
            df,
            annotationType,
            tsvParserConfig.formatHeader.get,
            tsvParserConfig.reference)
        processAnnotation(annotation).dataFrame
      case AnnotationType.UnstructuredAnnotation => df
    }
  }

  /**
   * Process structured annotation
   *
   * @param annotation
   *   annotation object for processing
   * @throws RuntimeException
   *   validateCoordinatesWithReference throws exception when annotations falls outside of the
   *   length of a contig in reference
   * @return
   *   transformed and validated annotation
   */
  def processAnnotation(annotation: Annotation): Annotation = {
    val zeroBased = convertToZeroBaseHalfEnd(annotation)

    val normalized: Annotation =
      (zeroBased.annotationType, tsvParserConfig.runLeftNormalization) match {
        case (AnnotationType.ChrStartEndRefAltZeroBase, true) => leftNormalize(zeroBased)
        case _ => zeroBased
      }
    normalized
  }

  /**
   * Convert Annotation to zero base half end
   *
   * Refer to https://plastid.readthedocs.io/en/latest/concepts/coordinates.html to know more
   * about the different coordinate system
   *
   * Transformation is done recursively. Annotations containing zero based coordinates are
   * returned
   *
   * @param annotation
   *   : Annotation object
   * @return
   *   Annotation with zero based coordinates.
   */
  def convertToZeroBaseHalfEnd(annotation: Annotation): Annotation = {
    val (_, start, end, ref, _) = FormatHeader.unapply(annotation.header)
    val df = annotation.dataFrame
    annotation.annotationType match {
      case _: AnnotationType.ZeroBase => annotation
      case AnnotationType.ChrPos =>
        val transformed = df.withColumn(end, col(start).cast("int"))
        convertToZeroBaseHalfEnd(
          annotation
            .copy(dataFrame = transformed, annotationType = AnnotationType.ChrStartEndOneBase))
      case AnnotationType.ChrStartEndOneBase =>
        val transformed = df.withColumn(start, col(start) - 1)
        convertToZeroBaseHalfEnd(
          annotation
            .copy(dataFrame = transformed, annotationType = AnnotationType.ChrStartEndZeroBase))
      case AnnotationType.ChrPosRefAlt =>
        val transformed =
          df.withColumn(end, (col(start) + length(col(ref)) - 1).cast("int"))
        convertToZeroBaseHalfEnd(
          annotation.copy(
            dataFrame = transformed,
            annotationType = AnnotationType.ChrStartEndRefAltOneBase))
      case AnnotationType.ChrStartEndRefAltOneBase =>
        val transformed = df.withColumn(start, col(start) - 1)
        convertToZeroBaseHalfEnd(
          annotation.copy(
            dataFrame = transformed,
            annotationType = AnnotationType.ChrStartEndRefAltZeroBase))
    }
  }

  /**
   * Run left normalization with glow and update dataframe with norm results accordingly.
   *
   * This is akin to running `glow.transform("normalize_variants", df, ...)` . Using the
   * NormalizeVariant transformer requires fixed column names.
   *
   * Therefore we use `normalize_variant`, but we need to replace the original columns with the
   * results manually
   *
   * This method will produce similar results with glow with one excpetion:
   *   - since we are not dealing with multi-allelic alt with TSV annotation, the alt allele will
   *     be reported as String instead of Array[String].
   *
   * @param annotation
   *   annotation instance containing dataframe and metadata
   * @throws RuntimeException
   *   when annnotation.AnnotationType is not ChrStartEndRefAltZeroBase since this is the only
   *   format that has all the fields required for normalization
   * @return
   *   left normalized annotation
   */
  def leftNormalize(annotation: Annotation): Annotation = {
    val (contigName, start, end, ref, alt) = FormatHeader.unapply(annotation.header)

    if (annotation.annotationType != AnnotationType.ChrStartEndRefAltZeroBase)
      throw new RuntimeException(s"""
           |LeftNormalizer.process only works with AnnotationType.ChrStartEndRefAltZeroBase.
           |Got: ${annotation.annotationType}""".stripMargin)

    val reference = annotation.reference.get
    val dataFrame = annotation.dataFrame

    val transformed = dataFrame.withColumn(alt, split(col(alt), ","))
    val normalization_expr =
      normalize_variant(col(contigName), col(start), col(end), col(ref), col(alt), reference.path)
    val normalized = transformed.withColumn(normalizationResultFieldName, normalization_expr)
    annotation.copy(dataFrame = updatedDFWithNormResult(normalized, annotation.header))
  }

  /**
   * Glow left normalize_variant Function creates a structType column containing the following
   * fields: normalized start, end, referenceAllele, alternateAlleles and normalizationStatus.
   * normalizationStatus is a structType containing fields `changed` and `error message`
   *
   * We want to replace the existing columns with the normalized results while storing the status
   * as a new column.
   *
   * We also want to convert alt from List[String] to String. we are NOT anticipating the alt to
   * be multi allelic.
   *
   * @param dataFrame
   *   containing normalized results
   * @return
   *   updated dataFrame
   */
  private def updatedDFWithNormResult(dataFrame: DataFrame, header: FormatHeader): DataFrame = {

    val (contigName, start, end, ref, alt) = FormatHeader.unapply(header)
    // fields names are defined in glow's VariantNormalizer._
    val inputToGlowNormalizedField: Map[String, String] = Map(
      contigName -> contigNameField.name,
      start -> startField.name,
      end -> endField.name,
      ref -> refAlleleField.name,
      alt -> alternateAllelesField.name)

    var replacedDF =
      Seq(start, end, ref, alt).foldLeft(dataFrame)((df, colName) => {
        val normalizedFieldName = inputToGlowNormalizedField(colName)
        df.withColumn(
          colName,
          when(
            col(s"$normalizationResultFieldName.$normalizationStatusFieldName.$changedFieldName"),
            col(s"$normalizationResultFieldName.$normalizedFieldName")).otherwise(col(colName)))
      })

    replacedDF = replacedDF.withColumn(alt, col(alt)(0))
    replacedDF.drop(normalizationResultFieldName)
  }
}
