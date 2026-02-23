// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.annotation.tsv

import com.amazon.vincent.job.annotation.FormatOptionsJsonProtocol._
import com.amazon.vincent.job.annotation.{AnnotationStoreOptions, FormatOptions}
import spray.json._

object DefaultAnnotationColNames extends Enumeration {
  type DefaultAnnotationColNames = Value

  val contigName: DefaultAnnotationColNames.Value = Value("chrom")
  val start: DefaultAnnotationColNames.Value = Value("start")
  val end: DefaultAnnotationColNames.Value = Value("end")
  val ref: DefaultAnnotationColNames.Value = Value("ref")
  val alt: DefaultAnnotationColNames.Value = Value("alt")
}

/**
 * * Class object to hold configs related to TSVParser
 *
 * @param inputFile
 *   path to input file
 * @param sparkOptions
 *   Options passed to spark creating dataframe from file. Full list of options found at
 *   https://spark.apache.org/docs/latest/sql-data-sources-csv.html#data-source-option
 * @param annotationType
 *   annotation type
 * @param reference
 *   path to reference file. File must be on local disk
 * @param schema
 *   User schema following Sparks SQL DDL
 * @param formatHeader
 *   mapping of annotation field to column header
 * @param sparkURL
 *   spark url
 * @param out
 *   optional path to out put file.
 */
case class TSVParserConfig(
    inputFile: String,
    schema: String,
    sparkOptions: Map[String, String] = TSVParserConfig.DEFAULTS.SPARK_OPTIONS,
    annotationType: AnnotationType.AnnotationFormat = AnnotationType.UnstructuredAnnotation,
    reference: Option[Reference] = None,
    runLeftNormalization: Boolean = false,
    formatHeader: Option[FormatHeader] = None,
    sparkURL: Option[String] = None,
    out: Option[String] = None)

/**
 * Extract Args specific to TSVParser from sys args
 *
 * While GlueArgParser.getResolvedOptions has a `options` parameter to include fields that the
 * user wil like to include, optional args are not supported and missing args will result in
 * error.
 *
 * Instead, argparse4j is used.
 *
 * When setting defaults with argparse4j, there are some interop problem with scala and java (see
 * https://github.com/argparse4j/argparse4j/issues/47). Therefore we are manaully setting defaults
 * below.
 */
object TSVParserConfig {

  object DEFAULTS {
    val SPARK_OPTIONS = Map("header" -> "true", "delimiter" -> "\t", "inferSchema" -> "true")
    val ANNOTATION_TYPE: AnnotationType.AnnotationFormat = AnnotationType.UnstructuredAnnotation
  }

  def parseSchemaString(schemaString: String): String = {
    val schemaMap = schemaString.parseJson.convertTo[List[Map[String, String]]]
    schemaMap.map(x => s"${x.keys.head} ${x.values.head}").mkString(" ,")
  }
  def parseFromGlueArgs(
      inputFile: String,
      formatOptionsString: String,
      storeOptionsString: String,
      reference: Option[String],
      runLeftNormalization: Boolean = false): TSVParserConfig = {

    val jsonAst = formatOptionsString.parseJson
    val sparkOptions = jsonAst.convertTo[FormatOptions].tsvOptions match {
      case Some(value) => value.readOptions.getOrElse(DEFAULTS.SPARK_OPTIONS)
      case None => DEFAULTS.SPARK_OPTIONS
    }

    val storeOptions =
      storeOptionsString.parseJson.convertTo[AnnotationStoreOptions].tsvStoreOptions.get
    val schema = parseSchemaString(storeOptions.schema.get)
    val annotationType = storeOptions.annotationType match {
      case Some(value) => AnnotationType.fromName(value)
      case _ => DEFAULTS.ANNOTATION_TYPE
    }
    val formatHeader = annotationType match {
      case AnnotationType.UnstructuredAnnotation => None
      case annotation: AnnotationType.StructuredAnnotation =>
        Some(FormatHeader(storeOptions.formatToHeader.get, annotation))
    }

    val refObject = if (reference.isDefined) Some(Reference(reference.get)) else None

    if (runLeftNormalization && refObject.isEmpty) {
      throw new RuntimeException("Unable to run left normalization without a reference")
    }

    new TSVParserConfig(
      inputFile = inputFile,
      schema = schema,
      sparkOptions = sparkOptions,
      runLeftNormalization = runLeftNormalization,
      annotationType = annotationType,
      reference = refObject,
      formatHeader = formatHeader)
  }
}

case class FormatHeader(
    contigName: String = DefaultAnnotationColNames.contigName.toString,
    start: String = DefaultAnnotationColNames.start.toString,
    end: String = DefaultAnnotationColNames.end.toString,
    ref: String = DefaultAnnotationColNames.ref.toString,
    alt: String = DefaultAnnotationColNames.alt.toString)

object FormatHeader {

  /**
   * Creates an instance of FormatHeader base on annotationType Object from a Map
   *
   * If there are any missing keys required for an annotationType, error will be thrown
   *
   * @param formatToHeaderMap
   *   map where the keys are the annotation fields' names and the values are the names of the
   *   columns found in the input file
   * @param annotationType
   *   annotation type of the input file
   * @throws java.util.NoSuchElementException:
   *   If there is a missing key in map that is required for a annotation type
   * @return
   *   instance of formatHeaders
   */
  def apply(
      formatToHeaderMap: Map[String, String],
      annotationType: AnnotationType.StructuredAnnotation): FormatHeader = {
    annotationType match {
      case AnnotationType.ChrPos =>
        new FormatHeader(formatToHeaderMap("CHR"), formatToHeaderMap("POS"), "end")

      case AnnotationType.ChrPosRefAlt =>
        new FormatHeader(
          formatToHeaderMap("CHR"),
          formatToHeaderMap("POS"),
          ref = formatToHeaderMap("REF"),
          alt = formatToHeaderMap("ALT"))
      case AnnotationType.ChrStartEndRefAltOneBase | AnnotationType.ChrStartEndRefAltZeroBase =>
        new FormatHeader(
          formatToHeaderMap("CHR"),
          formatToHeaderMap("START"),
          formatToHeaderMap("END"),
          formatToHeaderMap("REF"),
          formatToHeaderMap("ALT"))
      case AnnotationType.ChrStartEndZeroBase | AnnotationType.ChrStartEndOneBase =>
        new FormatHeader(
          formatToHeaderMap("CHR"),
          formatToHeaderMap("START"),
          formatToHeaderMap("END"))
    }
  }

  def unapply(formatHeader: FormatHeader): (String, String, String, String, String) = {
    (
      formatHeader.contigName,
      formatHeader.start,
      formatHeader.end,
      formatHeader.ref,
      formatHeader.alt)
  }
}
